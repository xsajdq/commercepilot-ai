import asyncio

from cp_domain.connection import Connection
from cp_shared.crypto import decrypt_credentials, encrypt_credentials
from sqlalchemy import select

from worker.celery_app import app
from worker.db import get_encryption_keys, session_scope


@app.task(name="worker.reencrypt_all_connections")
def reencrypt_all_connections() -> dict:
    """Ops-triggered maintenance task for an `ENCRYPTION_KEY` rotation
    (Phase 21 - see docs/security/secret-rotation.md): decrypts every
    `Connection.encrypted_credentials` row with the full key list
    (current + previous, from `get_encryption_keys`) and re-encrypts it
    under the current key alone, migrating rows still written under a
    key that's about to be retired.

    Safe to run more than once - a row already under the current key
    just gets rewritten to new (still valid) ciphertext, never a
    decryption failure. Never triggered automatically: a human runs
    this deliberately, after setting `ENCRYPTION_KEY_PREVIOUS` and
    before removing it.
    """
    return asyncio.run(_reencrypt_all_connections())


async def _reencrypt_all_connections() -> dict:
    keys = get_encryption_keys()
    current_key = keys[0]
    migrated = 0
    failed: list[str] = []

    async with session_scope() as db:
        connections = list(await db.scalars(select(Connection)))
        for connection in connections:
            if connection.encrypted_credentials is None:
                continue
            try:
                credentials = decrypt_credentials(connection.encrypted_credentials, key=keys)
            except Exception:  # noqa: BLE001 - report and keep migrating the rest
                failed.append(str(connection.id))
                continue
            connection.encrypted_credentials = encrypt_credentials(credentials, key=current_key)
            migrated += 1
        await db.commit()

    return {"migrated": migrated, "failed": failed}
