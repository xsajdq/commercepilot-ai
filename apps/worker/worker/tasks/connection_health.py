import asyncio
import uuid

from cp_connectors.exceptions import ConnectorAuthError, ConnectorError
from cp_domain.connection import Connection, ConnectionStatus
from cp_shared.crypto import decrypt_credentials
from cp_sync.connector_factory import build_connector
from sqlalchemy import select

from worker.celery_app import app
from worker.db import get_encryption_keys, session_scope


@app.task(name="worker.test_connection")
def test_connection(tenant_id: str, connection_id: str) -> dict:
    """Phase 22: a real pre-flight check, not an optimistic assumption.

    `POST /connections` used to mark a brand-new connection CONNECTED
    the instant it was created, with nothing ever actually calling the
    platform's API until the next scheduled sync - a pilot merchant with
    a typo'd API key wouldn't find out until up to 24 hours later. This
    makes one real, lightweight, read-only call (`get_products(limit=1)`)
    and records the real outcome, the same way a full sync would if
    credentials were wrong - just without touching any product data.

    Safe to call anytime, not just at creation: re-running this is how a
    merchant (or support, during the beta) checks "is this actually
    still working" after rotating an API key on the platform's own side.
    """
    return asyncio.run(_test_connection(uuid.UUID(tenant_id), uuid.UUID(connection_id)))


async def _test_connection(tenant_id: uuid.UUID, connection_id: uuid.UUID) -> dict:
    async with session_scope() as db:
        connection = await db.scalar(
            select(Connection).where(
                Connection.id == connection_id, Connection.tenant_id == tenant_id
            )
        )
        if connection is None:
            raise ValueError(f"Connection {connection_id} not found for tenant {tenant_id}")

        try:
            credentials = decrypt_credentials(
                connection.encrypted_credentials, key=get_encryption_keys()
            )
            connector = build_connector(connection, credentials)
            await connector.get_products(limit=1)
        except ConnectorAuthError as exc:
            connection.status = ConnectionStatus.ERROR
            connection.last_error = f"Authentication failed - check your credentials: {exc}"
            await db.commit()
            return {"connected": False, "error": connection.last_error}
        except ConnectorError as exc:
            connection.status = ConnectionStatus.ERROR
            connection.last_error = str(exc)
            await db.commit()
            return {"connected": False, "error": connection.last_error}
        except Exception as exc:  # noqa: BLE001 - any other failure is still a real, honest result
            connection.status = ConnectionStatus.ERROR
            connection.last_error = f"Unexpected error: {exc}"
            await db.commit()
            return {"connected": False, "error": connection.last_error}

        connection.status = ConnectionStatus.CONNECTED
        connection.last_error = None
        await db.commit()
        return {"connected": True, "error": None}
