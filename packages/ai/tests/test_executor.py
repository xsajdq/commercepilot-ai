import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from cp_domain.audit_event import ActorType, AuditEvent, AuditResult
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from cp_ai.tools import (
    ToolCall,
    ToolContext,
    ToolExecutor,
    ToolPermission,
    ToolRegistry,
    ToolResult,
    ToolRiskLevel,
    ToolSchema,
)


class _Args(BaseModel):
    value: int = 0


def _mock_db() -> AsyncSession:
    """A fake AsyncSession: `.add` is sync (as it really is on
    AsyncSession) so it doesn't produce an un-awaited-coroutine warning,
    `.commit` is async - matching the two calls `ToolExecutor._audit`
    actually makes, without needing a real database for these
    executor-mechanics tests (see apps/api's test suite for the
    DB-integration coverage)."""
    db = MagicMock(spec=AsyncSession)
    db.commit = AsyncMock()
    return db


def _context() -> ToolContext:
    return ToolContext(tenant_id=uuid.uuid4(), actor_type=ActorType.AI_AGENT)


def _tool(name: str, *, risk: ToolRiskLevel, mutates: bool, handler) -> ToolSchema:
    return ToolSchema(
        name=name,
        description="test tool",
        args_model=_Args,
        permission=ToolPermission(risk_level=risk, mutates=mutates),
        handler=handler,
    )


class TestToolExecutor:
    async def test_unknown_tool_fails_without_touching_db(self) -> None:
        db = _mock_db()
        executor = ToolExecutor(ToolRegistry(), db)

        result = await executor.execute(ToolCall(name="ghost", arguments={}), _context())

        assert result.success is False
        assert "ghost" in result.error
        db.add.assert_not_called()
        db.commit.assert_not_called()

    async def test_invalid_arguments_fail_before_handler_runs(self) -> None:
        registry = ToolRegistry()
        called = False

        async def handler(args, context, db):
            nonlocal called
            called = True
            return ToolResult.ok()

        registry.register(_tool("t", risk=ToolRiskLevel.LOW, mutates=False, handler=handler))
        db = _mock_db()
        executor = ToolExecutor(registry, db)

        result = await executor.execute(
            ToolCall(name="t", arguments={"value": "not-an-int"}), _context()
        )

        assert result.success is False
        assert called is False
        db.add.assert_not_called()

    @pytest.mark.parametrize("risk", [ToolRiskLevel.MEDIUM, ToolRiskLevel.HIGH])
    async def test_medium_and_high_risk_short_circuit_without_running_handler(
        self, risk: ToolRiskLevel
    ) -> None:
        registry = ToolRegistry()
        called = False

        async def handler(args, context, db):
            nonlocal called
            called = True
            return ToolResult.ok()

        registry.register(_tool("t", risk=risk, mutates=True, handler=handler))
        db = _mock_db()
        executor = ToolExecutor(registry, db)

        result = await executor.execute(ToolCall(name="t", arguments={}), _context())

        assert result.success is False
        assert result.requires_approval is True
        assert called is False
        db.add.assert_not_called()
        db.commit.assert_not_called()

    async def test_low_risk_read_only_tool_executes_without_audit_log(self) -> None:
        registry = ToolRegistry()

        async def handler(args, context, db):
            return ToolResult.ok({"answer": 42})

        registry.register(_tool("t", risk=ToolRiskLevel.LOW, mutates=False, handler=handler))
        db = _mock_db()
        executor = ToolExecutor(registry, db)

        result = await executor.execute(ToolCall(name="t", arguments={}), _context())

        assert result.success is True
        assert result.data == {"answer": 42}
        db.add.assert_not_called()
        db.commit.assert_not_called()

    async def test_low_risk_mutating_tool_writes_audit_log_on_success(self) -> None:
        registry = ToolRegistry()
        context = _context()

        async def handler(args, ctx, db):
            return ToolResult.ok(
                {"new": "value"},
                entity_type="widget",
                entity_id=uuid.uuid4(),
                before={"old": "value"},
                after={"new": "value"},
            )

        registry.register(_tool("t", risk=ToolRiskLevel.LOW, mutates=True, handler=handler))
        db = _mock_db()
        executor = ToolExecutor(registry, db)

        result = await executor.execute(ToolCall(name="t", arguments={}), context)

        assert result.success is True
        db.commit.assert_awaited_once()
        [event] = [c.args[0] for c in db.add.call_args_list]
        assert isinstance(event, AuditEvent)
        assert event.tenant_id == context.tenant_id
        assert event.actor_type == ActorType.AI_AGENT
        assert event.action == "t"
        assert event.entity_type == "widget"
        assert event.before == {"old": "value"}
        assert event.after == {"new": "value"}
        assert event.result == AuditResult.SUCCESS

    async def test_low_risk_mutating_tool_writes_failed_audit_log_on_handler_error(self) -> None:
        registry = ToolRegistry()

        async def handler(args, context, db):
            raise RuntimeError("boom")

        registry.register(_tool("t", risk=ToolRiskLevel.LOW, mutates=True, handler=handler))
        db = _mock_db()
        executor = ToolExecutor(registry, db)

        result = await executor.execute(ToolCall(name="t", arguments={}), _context())

        assert result.success is False
        assert result.error == "boom"
        [event] = [c.args[0] for c in db.add.call_args_list]
        assert event.result == AuditResult.FAILURE
        assert event.error_message == "boom"

    async def test_low_risk_mutating_tool_returning_a_failure_still_audits(self) -> None:
        registry = ToolRegistry()

        async def handler(args, context, db):
            return ToolResult.fail("could not apply change")

        registry.register(_tool("t", risk=ToolRiskLevel.LOW, mutates=True, handler=handler))
        db = _mock_db()
        executor = ToolExecutor(registry, db)

        result = await executor.execute(ToolCall(name="t", arguments={}), _context())

        assert result.success is False
        [event] = [c.args[0] for c in db.add.call_args_list]
        assert event.result == AuditResult.FAILURE
        assert event.error_message == "could not apply change"
