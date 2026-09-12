import os

# Must be set before any `app.*` module is imported: app.db.base creates its
# async engine from get_settings() at import time, and Settings is cached.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://commercepilot:commercepilot@localhost:5432/commercepilot_test",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "test-secret-key-do-not-use-in-production")

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import models  # noqa: E402,F401  (registers metadata)
from app.db.base import Base, async_session_factory, engine  # noqa: E402
from app.main import app  # noqa: E402

_TABLES = ", ".join(
    t.name for t in reversed(Base.metadata.sorted_tables)
)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _database_schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables():
    yield
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE TABLE {_TABLES} RESTART IDENTITY CASCADE"))


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def db_session():
    async with async_session_factory() as session:
        yield session
