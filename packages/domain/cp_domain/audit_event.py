import enum
import uuid
from datetime import datetime

from cp_shared.db import Base, TenantScopedMixin, UUIDPrimaryKeyMixin
from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class ActorType(str, enum.Enum):
    USER = "user"
    AI_AGENT = "ai_agent"
    SYSTEM = "system"


class AuditResult(str, enum.Enum):
    SUCCESS = "success"
    FAILURE = "failure"


class AuditEvent(UUIDPrimaryKeyMixin, TenantScopedMixin, Base):
    """Immutable log of every mutation - no updated_at, rows are never
    changed after being written. This is what `before`/`after` price
    history, approval trails, etc. read from, rather than each table
    keeping its own history."""

    __tablename__ = "audit_events"

    actor_type: Mapped[ActorType] = mapped_column(
        SAEnum(ActorType, name="actor_type"), nullable=False
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    before: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("approvals.id", ondelete="SET NULL"), nullable=True
    )
    ai_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ai_prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    result: Mapped[AuditResult] = mapped_column(
        SAEnum(AuditResult, name="audit_result"), nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
