import uuid
from datetime import datetime
from typing import Annotated

from cp_domain.ai_job import AIJob, AIJobStatus
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_membership
from app.core.celery_client import get_celery_client
from app.db.base import get_db
from app.db.models.membership import Membership

router = APIRouter(prefix="/catalog", tags=["catalog"])


class TaskTriggeredResponse(BaseModel):
    task_id: str


class CatalogIssueOut(BaseModel):
    type: str
    severity: str
    entity_type: str
    entity_id: str
    sku: str
    message: str


class CatalogAuditOut(BaseModel):
    id: uuid.UUID
    status: AIJobStatus
    products_scanned: int | None = None
    recommendations_proposed: int | None = None
    issues: list[CatalogIssueOut] = []
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


def _to_audit_out(job: AIJob) -> CatalogAuditOut:
    # AIJob.output_payload is a free-form JSONB bag (Phase 2 scaffold) -
    # only the catalog agent's own shape (see worker.tasks.catalog) is
    # meaningful here, so read it defensively rather than assume it's
    # ever populated (a RUNNING or FAILED job has none yet).
    payload = job.output_payload or {}
    return CatalogAuditOut(
        id=job.id,
        status=job.status,
        products_scanned=payload.get("products_scanned"),
        recommendations_proposed=payload.get("recommendations_proposed"),
        issues=[CatalogIssueOut(**issue) for issue in payload.get("issues", [])],
        error_message=job.error_message,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


@router.post("/audit", response_model=TaskTriggeredResponse)
async def trigger_catalog_audit(
    membership: Annotated[Membership, Depends(get_current_membership)],
) -> TaskTriggeredResponse:
    result = get_celery_client().send_task(
        "worker.run_catalog_audit", args=[str(membership.tenant_id)]
    )
    return TaskTriggeredResponse(task_id=result.id)


@router.get("/audits", response_model=list[CatalogAuditOut])
async def list_catalog_audits(
    db: Annotated[AsyncSession, Depends(get_db)],
    membership: Annotated[Membership, Depends(get_current_membership)],
) -> list[CatalogAuditOut]:
    jobs = await db.scalars(
        select(AIJob)
        .where(AIJob.tenant_id == membership.tenant_id, AIJob.agent_type == "catalog")
        .order_by(AIJob.created_at.desc())
        .limit(50)
    )
    return [_to_audit_out(job) for job in jobs]
