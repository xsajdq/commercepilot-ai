import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from cp_shared.db import Base
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

__all__ = ["Base", "get_encryption_key", "session_scope"]

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


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession]:
    async with async_session_factory() as session:
        yield session
