import asyncio
import uuid

import pytest
from cp_connectors.exceptions import ConnectorAuthError, ConnectorError
from cp_connectors.mock import MockConnector
from cp_domain.connection import Connection, ConnectionStatus

from tests.conftest import make_connection, make_tenant
from worker.db import async_session_factory
from worker.tasks.connection_health import test_connection as run_test_connection


def _get_connection(connection_id: uuid.UUID) -> Connection:
    async def _run() -> Connection:
        async with async_session_factory() as db:
            return await db.get(Connection, connection_id)

    return asyncio.run(_run())


class _BoomConnector:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def get_products(self, *, cursor=None, limit=50):
        raise self._exc


class TestTestConnectionTask:
    def test_marks_a_working_connection_connected_and_clears_the_error(
        self, monkeypatch
    ) -> None:
        tenant_id = make_tenant()
        connection_id = make_connection(tenant_id, {"access_token": "tok"})
        # Seed a prior failure so we can prove this call actually clears it.
        async def _seed_error() -> None:
            async with async_session_factory() as db:
                connection = await db.get(Connection, connection_id)
                connection.status = ConnectionStatus.ERROR
                connection.last_error = "stale failure from before"
                await db.commit()

        asyncio.run(_seed_error())

        monkeypatch.setattr(
            "worker.tasks.connection_health.build_connector",
            lambda connection, credentials: MockConnector(),
        )

        result = run_test_connection.run(str(tenant_id), str(connection_id))

        assert result == {"connected": True, "error": None}
        connection = _get_connection(connection_id)
        assert connection.status is ConnectionStatus.CONNECTED
        assert connection.last_error is None

    def test_reports_a_clear_message_for_an_auth_failure(self, monkeypatch) -> None:
        tenant_id = make_tenant()
        connection_id = make_connection(tenant_id, {"access_token": "bad-token"})

        monkeypatch.setattr(
            "worker.tasks.connection_health.build_connector",
            lambda connection, credentials: _BoomConnector(
                ConnectorAuthError("WooCommerce rejected credentials: 401")
            ),
        )

        result = run_test_connection.run(str(tenant_id), str(connection_id))

        assert result["connected"] is False
        assert "Authentication failed" in result["error"]
        connection = _get_connection(connection_id)
        assert connection.status is ConnectionStatus.ERROR
        assert "Authentication failed" in connection.last_error

    def test_reports_a_generic_connector_error_as_is(self, monkeypatch) -> None:
        tenant_id = make_tenant()
        connection_id = make_connection(tenant_id, {"access_token": "tok"})

        monkeypatch.setattr(
            "worker.tasks.connection_health.build_connector",
            lambda connection, credentials: _BoomConnector(
                ConnectorError("platform returned a 500")
            ),
        )

        result = run_test_connection.run(str(tenant_id), str(connection_id))

        assert result == {"connected": False, "error": "platform returned a 500"}

    def test_never_crashes_on_a_totally_unexpected_exception(self, monkeypatch) -> None:
        tenant_id = make_tenant()
        connection_id = make_connection(tenant_id, {"access_token": "tok"})

        monkeypatch.setattr(
            "worker.tasks.connection_health.build_connector",
            lambda connection, credentials: _BoomConnector(RuntimeError("boom")),
        )

        result = run_test_connection.run(str(tenant_id), str(connection_id))

        assert result["connected"] is False
        assert "Unexpected error" in result["error"]

    def test_raises_for_unknown_connection(self) -> None:
        with pytest.raises(ValueError, match="not found"):
            run_test_connection.run(str(uuid.uuid4()), str(uuid.uuid4()))
