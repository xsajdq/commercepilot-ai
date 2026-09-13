import asyncio
import uuid

from cp_domain.connection import Connection
from cp_shared.crypto import decrypt_credentials
from cp_sync.connector_factory import build_connector
from cp_sync.products import sync_products
from sqlalchemy import select

from worker.celery_app import app
from worker.db import get_encryption_key, session_scope


@app.task(name="worker.sync_connection")
def sync_connection(tenant_id: str, connection_id: str) -> dict:
    """Celery entrypoint for Phase 6 sync: fetches every product from one
    `Connection`'s marketplace and upserts it into the domain model.

    Never called with unvalidated input from the AI or an HTTP handler
    directly - a caller (API route, beat schedule) is responsible for
    resolving `tenant_id`/`connection_id` from an authenticated/trusted
    context first (CLAUDE.md: never trust tenant_id from client input).

    Bridges Celery's sync task interface to the async DB/connector stack
    with `asyncio.run` - this task does its own I/O and must never be
    invoked inline from an HTTP request handler (CLAUDE.md: background
    work is Celery-only).
    """
    return asyncio.run(_sync_connection(uuid.UUID(tenant_id), uuid.UUID(connection_id)))


async def _sync_connection(tenant_id: uuid.UUID, connection_id: uuid.UUID) -> dict:
    async with session_scope() as db:
        connection = await db.scalar(
            select(Connection).where(
                Connection.id == connection_id, Connection.tenant_id == tenant_id
            )
        )
        if connection is None:
            raise ValueError(f"Connection {connection_id} not found for tenant {tenant_id}")

        credentials = decrypt_credentials(
            connection.encrypted_credentials, key=get_encryption_key()
        )
        connector = build_connector(connection, credentials)

        result = await sync_products(
            db, tenant_id=tenant_id, connection=connection, connector=connector
        )
        return result.to_dict()
