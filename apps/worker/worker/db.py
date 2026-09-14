import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from cp_shared.db import Base, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.pool import NullPool

__all__ = ["Base", "get_encryption_key", "get_encryption_keys", "session_scope"]


class _TenantRef(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A minimal stand-in for apps/api's real `Tenant` model, same
    `tenants` table - apps/worker must never import apps/api's code to
    get the real class, but every `TenantScopedMixin` table's
    `ForeignKey("tenants.id")` needs a mapped `Table` object to resolve
    against *in this process's own metadata* the first time any such row
    is flushed here (sync, a pricing/content recommendation, ...) - not
    just at schema-creation time in a test. SQLAlchemy resolves that FK
    to determine flush ordering even when the tenant_id value itself
    isn't being touched, so without this, every tenant-scoped insert
    from apps/worker fails with `NoReferencedTableError`, no matter how
    innocuous the FK column's actual value is. Never queried through
    this class - the real row was created by apps/api.
    """

    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)


class _UserRef(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Same reasoning as `_TenantRef`, for `Approval.decided_by`'s FK to
    `users.id` - `cp_policies.submit_for_approval` creates an `Approval`
    row (with `decided_by` still `NULL` until a human decides), and that
    insert needs `users` resolvable for the exact same flush-ordering
    reason."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)

# Mirrors apps/api/app/db/base.py's engine setup, but reads its own
# environment directly (worker.celery_app already does this rather than
# using pydantic-settings) since apps/worker must not import from apps/api.
_DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://commercepilot:commercepilot@postgres:5432/commercepilot"
)

# NullPool, not a pooled engine: each Celery task invocation bridges into
# asyncio via its own `asyncio.run(...)` call (see worker/tasks/sync.py),
# which tears down its event loop when the task returns. A pooled asyncpg
# connection checked out under one task's loop and reused by the next
# task's (new) loop fails with "Future attached to a different loop" -
# NullPool opens a fresh connection per checkout instead of keeping one
# alive across loops.
engine = create_async_engine(_DATABASE_URL, poolclass=NullPool)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


def get_encryption_key() -> str:
    """Reads ENCRYPTION_KEY lazily (not at import time) so tests can set
    it via monkeypatch/env before a task actually needs to decrypt.
    """
    return os.environ["ENCRYPTION_KEY"]


def get_encryption_keys() -> list[str]:
    """Current key first, optional `ENCRYPTION_KEY_PREVIOUS` appended
    only during a rotation window - mirrors apps/api's
    `Settings.encryption_keys` (see its own docstring and
    docs/security/secret-rotation.md). Every real decrypt of an
    existing `Connection.encrypted_credentials` row should use this,
    not the singular key, so a row written before a rotation still
    decrypts correctly during the overlap window.
    """
    keys = [get_encryption_key()]
    previous = os.environ.get("ENCRYPTION_KEY_PREVIOUS")
    if previous:
        keys.append(previous)
    return keys


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession]:
    async with async_session_factory() as session:
        yield session
