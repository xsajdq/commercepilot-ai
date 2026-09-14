import os
import uuid

# Must be set before any `app.*` module is imported: app.db.base creates its
# async engine from get_settings() at import time, and Settings is cached.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://commercepilot:commercepilot@localhost:5432/commercepilot_test",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "test-secret-key-do-not-use-in-production")

import pytest_asyncio  # noqa: E402
from cp_domain.connection import Connection, ConnectionPlatform, ConnectionStatus  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.core.redis_client import get_redis_client  # noqa: E402
from app.db import models  # noqa: E402,F401  (registers metadata)
from app.db.base import Base, async_session_factory, engine  # noqa: E402
from app.db.models.tenant import Tenant  # noqa: E402
from app.db.models.user import User  # noqa: E402
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


@pytest_asyncio.fixture(autouse=True)
async def _clean_rate_limits():
    """Runs *before* every test (not just after, like `_clean_tables`):
    the Phase 21 rate limiter counts real requests in real Redis keyed
    by client IP, and every test's `AsyncClient` looks like the same IP
    to it - without resetting the counter at the start of each test, an
    unrelated test earlier in the same run could exhaust an auth-route
    test's budget before it even starts."""
    client = get_redis_client()
    try:
        keys = [key async for key in client.scan_iter(match="ratelimit:*")]
        if keys:
            await client.delete(*keys)
    finally:
        await client.aclose()
    yield


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def db_session():
    async with async_session_factory() as session:
        yield session


async def make_tenant(db: AsyncSession, name: str = "Test Tenant") -> Tenant:
    tenant = Tenant(name=name, slug=name.lower().replace(" ", "-") + "-" + uuid.uuid4().hex[:8])
    db.add(tenant)
    await db.commit()
    return tenant


async def make_user(db: AsyncSession, email: str | None = None) -> User:
    email = email or f"approver-{uuid.uuid4().hex[:8]}@test.com"
    user = User(email=email, hashed_password="not-a-real-hash", full_name="Test Approver")
    db.add(user)
    await db.commit()
    return user


async def make_connection(
    db: AsyncSession, tenant: Tenant, name: str = "My Woo Store"
) -> Connection:
    connection = Connection(
        tenant_id=tenant.id,
        platform=ConnectionPlatform.WOOCOMMERCE,
        name=name,
        status=ConnectionStatus.CONNECTED,
    )
    db.add(connection)
    await db.commit()
    return connection
