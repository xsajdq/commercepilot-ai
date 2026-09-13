import asyncio
import os
import uuid
from decimal import Decimal

# Must be set before `worker.db`/`worker.celery_app` are imported: both
# read the environment at import time.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://commercepilot:commercepilot@localhost:5432/commercepilot_test",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ENCRYPTION_KEY", "PkZQhLxgmytMSC4Pu32Jh6FT5i_UN5bGclRzJ9Or-Wk=")

import pytest  # noqa: E402
from cp_domain.connection import Connection, ConnectionPlatform, ConnectionStatus  # noqa: E402
from cp_domain.offer import Offer  # noqa: E402
from cp_domain.price import Price  # noqa: E402
from cp_domain.product import Product  # noqa: E402
from cp_domain.variant import Variant  # noqa: E402
from cp_shared.crypto import encrypt_credentials  # noqa: E402
from cp_shared.db import Base, TimestampMixin, UUIDPrimaryKeyMixin  # noqa: E402
from sqlalchemy import String, text  # noqa: E402
from sqlalchemy.orm import Mapped, mapped_column  # noqa: E402

from worker.db import async_session_factory, engine, get_encryption_key  # noqa: E402


class _Tenant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Test-only mirror of apps/api's Tenant model (same `tenants` table):
    apps/worker must not import apps/api's package just to satisfy
    Connection.tenant_id's FK in a test fixture.
    """

    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)


class _User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Test-only mirror of apps/api's User model (same `users` table),
    needed only so `Approval.decided_by`'s FK has a target table when
    building the full schema - the sync task never touches it.
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)


_TABLES = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))


@pytest.fixture(scope="session", autouse=True)
def _database_schema():
    async def _create() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create())
    yield

    async def _drop() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    asyncio.run(_drop())


@pytest.fixture(autouse=True)
def _clean_tables():
    yield

    async def _truncate() -> None:
        async with engine.begin() as conn:
            await conn.execute(text(f"TRUNCATE TABLE {_TABLES} RESTART IDENTITY CASCADE"))

    asyncio.run(_truncate())


def make_tenant(name: str = "Test Tenant") -> uuid.UUID:
    async def _create() -> uuid.UUID:
        async with async_session_factory() as db:
            tenant = _Tenant(
                name=name, slug=name.lower().replace(" ", "-") + "-" + uuid.uuid4().hex[:8]
            )
            db.add(tenant)
            await db.commit()
            return tenant.id

    return asyncio.run(_create())


def make_connection(
    tenant_id: uuid.UUID,
    credentials: dict,
    *,
    platform: ConnectionPlatform = ConnectionPlatform.WOOCOMMERCE,
    name: str = "My Woo Store",
) -> uuid.UUID:
    async def _create() -> uuid.UUID:
        async with async_session_factory() as db:
            connection = Connection(
                tenant_id=tenant_id,
                platform=platform,
                name=name,
                status=ConnectionStatus.CONNECTED,
                encrypted_credentials=encrypt_credentials(credentials, key=get_encryption_key()),
            )
            db.add(connection)
            await db.commit()
            return connection.id

    return asyncio.run(_create())


def make_product(
    tenant_id: uuid.UUID,
    *,
    sku: str = "SKU-1",
    name: str = "Test product",
    description: str | None = "Old description",
    ean: str | None = None,
) -> uuid.UUID:
    async def _create() -> uuid.UUID:
        async with async_session_factory() as db:
            product = Product(
                tenant_id=tenant_id, sku=sku, name=name, description=description, ean=ean
            )
            db.add(product)
            await db.commit()
            return product.id

    return asyncio.run(_create())


def make_offer_with_price(
    tenant_id: uuid.UUID,
    connection_id: uuid.UUID,
    *,
    sku: str = "SKU-1",
    cost: Decimal | None = Decimal("60"),
    price_amount: Decimal = Decimal("100.00"),
) -> uuid.UUID:
    async def _create() -> uuid.UUID:
        async with async_session_factory() as db:
            product = Product(tenant_id=tenant_id, sku=sku, name="Test product", cost=cost)
            db.add(product)
            await db.flush()
            variant = Variant(tenant_id=tenant_id, product_id=product.id, sku=sku)
            db.add(variant)
            await db.flush()
            offer = Offer(tenant_id=tenant_id, connection_id=connection_id, variant_id=variant.id)
            db.add(offer)
            await db.flush()
            db.add(Price(tenant_id=tenant_id, offer_id=offer.id, amount=price_amount))
            await db.commit()
            return offer.id

    return asyncio.run(_create())
