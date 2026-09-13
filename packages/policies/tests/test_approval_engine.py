import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from cp_ai.tools import ToolPermission, ToolRegistry, ToolResult, ToolRiskLevel, ToolSchema
from cp_domain.approval import Approval, ApprovalStatus
from cp_domain.recommendation import (
    Recommendation,
    RecommendationStatus,
    RecommendationType,
    RiskLevel,
)
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from cp_policies.approval_engine import (
    RecommendationNotFoundError,
    RecommendationNotPendingError,
    approve,
    reject,
    submit_for_approval,
)


def _mock_db(*scalar_results: object) -> AsyncSession:
    db = MagicMock(spec=AsyncSession)
    db.commit = AsyncMock()
    if scalar_results:
        db.scalar = AsyncMock(side_effect=list(scalar_results))
    return db


def _recommendation(
    *, status=RecommendationStatus.PENDING_APPROVAL, payload=None
) -> Recommendation:
    return Recommendation(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        type=RecommendationType.PRICE_CHANGE,
        risk_level=RiskLevel.HIGH,
        status=status,
        entity_type="offer",
        entity_id=uuid.uuid4(),
        title="Lower price",
        payload=payload or {"tool_name": "noop", "tool_arguments": {}},
    )


def _approval(recommendation: Recommendation, *, status=ApprovalStatus.PENDING) -> Approval:
    return Approval(
        id=uuid.uuid4(),
        tenant_id=recommendation.tenant_id,
        recommendation_id=recommendation.id,
        status=status,
    )


class _Args(BaseModel):
    value: int = 0


def _register_tool(registry: ToolRegistry, name: str, *, mutates: bool, handler) -> None:
    registry.register(
        ToolSchema(
            name=name,
            description="test tool",
            args_model=_Args,
            permission=ToolPermission(risk_level=ToolRiskLevel.HIGH, mutates=mutates),
            handler=handler,
        )
    )


class TestSubmitForApproval:
    async def test_rejects_a_recommendation_that_is_not_proposed(self) -> None:
        recommendation = _recommendation(status=RecommendationStatus.APPROVED)
        db = _mock_db()

        with pytest.raises(RecommendationNotPendingError):
            await submit_for_approval(db, recommendation)

    async def test_moves_proposed_to_pending_approval(self) -> None:
        recommendation = _recommendation(status=RecommendationStatus.PROPOSED)
        db = _mock_db()

        approval = await submit_for_approval(db, recommendation)

        assert recommendation.status is RecommendationStatus.PENDING_APPROVAL
        assert approval.status is ApprovalStatus.PENDING
        assert approval.recommendation_id == recommendation.id
        db.commit.assert_awaited_once()


class TestReject:
    async def test_unknown_recommendation_raises(self) -> None:
        db = _mock_db(None)

        with pytest.raises(RecommendationNotFoundError):
            await reject(
                db, tenant_id=uuid.uuid4(), recommendation_id=uuid.uuid4(), decided_by=uuid.uuid4()
            )

    async def test_already_decided_approval_raises(self) -> None:
        recommendation = _recommendation()
        approval = _approval(recommendation, status=ApprovalStatus.APPROVED)
        db = _mock_db(recommendation, approval)

        with pytest.raises(RecommendationNotPendingError):
            await reject(
                db,
                tenant_id=recommendation.tenant_id,
                recommendation_id=recommendation.id,
                decided_by=uuid.uuid4(),
            )

    async def test_rejecting_never_calls_any_tool(self) -> None:
        recommendation = _recommendation()
        approval = _approval(recommendation)
        db = _mock_db(recommendation, approval)
        decided_by = uuid.uuid4()

        result = await reject(
            db,
            tenant_id=recommendation.tenant_id,
            recommendation_id=recommendation.id,
            decided_by=decided_by,
            decision_reason="too aggressive",
        )

        assert result.status is RecommendationStatus.REJECTED
        assert approval.status is ApprovalStatus.REJECTED
        assert approval.decided_by == decided_by
        assert approval.decision_reason == "too aggressive"
        # No audit log for a rejection - nothing was mutated.
        db.add.assert_not_called()


class TestApprove:
    async def test_unknown_recommendation_raises(self) -> None:
        db = _mock_db(None)
        registry = ToolRegistry()

        with pytest.raises(RecommendationNotFoundError):
            await approve(
                db,
                registry,
                tenant_id=uuid.uuid4(),
                recommendation_id=uuid.uuid4(),
                decided_by=uuid.uuid4(),
            )

    async def test_successful_execution_marks_success_and_audits(self) -> None:
        recommendation = _recommendation(
            payload={"tool_name": "grant_discount", "tool_arguments": {"value": 5}}
        )
        approval = _approval(recommendation)
        db = _mock_db(recommendation, approval)
        registry = ToolRegistry()

        async def handler(args, context, db):
            return ToolResult.ok(
                {"discount": args.value},
                entity_type="offer",
                entity_id=recommendation.entity_id,
                before={"discount": 0},
                after={"discount": args.value},
            )

        _register_tool(registry, "grant_discount", mutates=True, handler=handler)
        decided_by = uuid.uuid4()

        result = await approve(
            db,
            registry,
            tenant_id=recommendation.tenant_id,
            recommendation_id=recommendation.id,
            decided_by=decided_by,
        )

        assert result.status is RecommendationStatus.SUCCESS
        assert approval.status is ApprovalStatus.APPROVED
        assert approval.decided_by == decided_by
        [event] = [c.args[0] for c in db.add.call_args_list]
        assert event.action == "grant_discount"
        assert event.approval_id == approval.id
        assert event.after == {"discount": 5}

    async def test_failing_handler_marks_failed_and_still_audits(self) -> None:
        recommendation = _recommendation(
            payload={"tool_name": "grant_discount", "tool_arguments": {"value": 5}}
        )
        approval = _approval(recommendation)
        db = _mock_db(recommendation, approval)
        registry = ToolRegistry()

        async def handler(args, context, db):
            raise RuntimeError("marketplace rejected the change")

        _register_tool(registry, "grant_discount", mutates=True, handler=handler)

        result = await approve(
            db,
            registry,
            tenant_id=recommendation.tenant_id,
            recommendation_id=recommendation.id,
            decided_by=uuid.uuid4(),
        )

        assert result.status is RecommendationStatus.FAILED
        [event] = [c.args[0] for c in db.add.call_args_list]
        assert event.error_message == "marketplace rejected the change"

    async def test_missing_tool_still_ends_terminal_and_audited(self) -> None:
        recommendation = _recommendation(
            payload={"tool_name": "no_longer_exists", "tool_arguments": {}}
        )
        approval = _approval(recommendation)
        db = _mock_db(recommendation, approval)
        registry = ToolRegistry()

        result = await approve(
            db,
            registry,
            tenant_id=recommendation.tenant_id,
            recommendation_id=recommendation.id,
            decided_by=uuid.uuid4(),
        )

        assert result.status is RecommendationStatus.FAILED
        db.add.assert_called_once()

    async def test_read_only_tool_is_not_audited(self) -> None:
        recommendation = _recommendation(
            payload={"tool_name": "peek", "tool_arguments": {}}
        )
        approval = _approval(recommendation)
        db = _mock_db(recommendation, approval)
        registry = ToolRegistry()

        async def handler(args, context, db):
            return ToolResult.ok({"answer": 1})

        _register_tool(registry, "peek", mutates=False, handler=handler)

        result = await approve(
            db,
            registry,
            tenant_id=recommendation.tenant_id,
            recommendation_id=recommendation.id,
            decided_by=uuid.uuid4(),
        )

        assert result.status is RecommendationStatus.SUCCESS
        db.add.assert_not_called()
