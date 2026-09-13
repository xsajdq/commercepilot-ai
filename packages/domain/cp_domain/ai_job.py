import enum
from datetime import datetime
from decimal import Decimal

from cp_shared.db import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import DateTime, Integer, Numeric, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class AIJobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class AIJob(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    """One AI agent run. tokens_used/cost_estimate exist now so the Phase
    31 cost guard has data to work with later - they're just recorded
    here, not enforced yet."""

    __tablename__ = "ai_jobs"

    agent_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[AIJobStatus] = mapped_column(
        SAEnum(AIJobStatus, name="ai_job_status"), nullable=False, default=AIJobStatus.QUEUED
    )
    input_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    output_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ai_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_estimate: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
