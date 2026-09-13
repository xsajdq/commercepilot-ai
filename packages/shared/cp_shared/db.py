import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Single shared declarative base and metadata for the whole backend.

    Both apps/api's own tables (users, tenants, memberships - platform
    concerns) and cp_domain's tables (products, orders, ... - the
    e-commerce domain) register on this one Base so Alembic sees one
    consistent schema and cross-package foreign keys (e.g. an Approval
    referencing users.id) resolve correctly.
    """


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class TenantScopedMixin:
    """Every business table outside the auth layer carries this. The
    backend always derives tenant_id from the authenticated session, never
    from client input - this column exists to enforce that at the
    database level (FK + required + indexed), not to invite trusting a
    client-supplied value here."""

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
