import asyncio
import uuid

import pytest
from cp_connectors.mock import MockConnector
from cp_connectors.types import ConnectorProduct
from cp_domain.product import Product
from sqlalchemy import func, select

from tests.conftest import make_connection, make_tenant
from worker.db import async_session_factory
from worker.tasks.sync import sync_connection


def _count_products() -> int:
    async def _run() -> int:
        async with async_session_factory() as db:
            return await db.scalar(select(func.count()).select_from(Product))

    return asyncio.run(_run())


class TestSyncConnectionTask:
    def test_run_decrypts_credentials_builds_connector_and_syncs(self, monkeypatch) -> None:
        tenant_id = make_tenant()
        connection_id = make_connection(
            tenant_id,
            {
                "store_url": "https://shop.example.com",
                "consumer_key": "ck",
                "consumer_secret": "cs",
            },
        )

        connector = MockConnector()
        asyncio.run(connector.create_product(ConnectorProduct(sku="WORKER-1", name="From worker")))

        seen_credentials = {}

        def fake_build_connector(connection, credentials):
            seen_credentials.update(credentials)
            return connector

        monkeypatch.setattr("worker.tasks.sync.build_connector", fake_build_connector)

        result = sync_connection.run(str(tenant_id), str(connection_id))

        assert result["products_upserted"] == 1
        assert result["fatal_error"] is None
        # The task decrypted the real stored credentials, not a stub.
        assert seen_credentials == {
            "store_url": "https://shop.example.com",
            "consumer_key": "ck",
            "consumer_secret": "cs",
        }
        assert _count_products() == 1

    def test_run_raises_for_connection_outside_tenant(self, monkeypatch) -> None:
        tenant_id = make_tenant()
        other_tenant_id = make_tenant("Other Tenant")
        connection_id = make_connection(tenant_id, {"access_token": "tok"})

        monkeypatch.setattr(
            "worker.tasks.sync.build_connector", lambda connection, credentials: MockConnector()
        )

        with pytest.raises(ValueError, match="not found"):
            sync_connection.run(str(other_tenant_id), str(connection_id))

    def test_run_raises_for_unknown_connection(self) -> None:
        with pytest.raises(ValueError, match="not found"):
            sync_connection.run(str(uuid.uuid4()), str(uuid.uuid4()))
