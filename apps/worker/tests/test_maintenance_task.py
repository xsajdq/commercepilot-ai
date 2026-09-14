import asyncio
import uuid

from cp_domain.connection import Connection
from cp_shared.crypto import decrypt_credentials
from cryptography.fernet import Fernet

from tests.conftest import make_connection, make_tenant
from worker.db import async_session_factory
from worker.tasks.maintenance import reencrypt_all_connections


def _get_connection(connection_id: uuid.UUID) -> Connection:
    async def _run() -> Connection:
        async with async_session_factory() as db:
            return await db.get(Connection, connection_id)

    return asyncio.run(_run())


class TestReencryptAllConnections:
    def test_migrates_a_row_written_under_the_old_key_to_the_new_key(self, monkeypatch) -> None:
        old_key = Fernet.generate_key().decode("utf-8")
        new_key = Fernet.generate_key().decode("utf-8")

        monkeypatch.setenv("ENCRYPTION_KEY", old_key)
        tenant_id = make_tenant()
        connection_id = make_connection(tenant_id, {"consumer_key": "ck", "consumer_secret": "cs"})

        # Simulate rotation: ops sets the new key as current, old one as
        # the fallback for the migration window.
        monkeypatch.setenv("ENCRYPTION_KEY", new_key)
        monkeypatch.setenv("ENCRYPTION_KEY_PREVIOUS", old_key)

        result = reencrypt_all_connections.run()

        assert result == {"migrated": 1, "failed": []}
        connection = _get_connection(connection_id)
        # Decryptable with the new key alone now - proves it was
        # actually rewritten, not just left as-is.
        assert decrypt_credentials(connection.encrypted_credentials, key=new_key) == {
            "consumer_key": "ck",
            "consumer_secret": "cs",
        }

    def test_is_idempotent_when_already_under_the_current_key(self, monkeypatch) -> None:
        key = Fernet.generate_key().decode("utf-8")
        monkeypatch.setenv("ENCRYPTION_KEY", key)
        tenant_id = make_tenant()
        make_connection(tenant_id, {"consumer_key": "ck"})

        first = reencrypt_all_connections.run()
        second = reencrypt_all_connections.run()

        assert first == {"migrated": 1, "failed": []}
        assert second == {"migrated": 1, "failed": []}

    def test_reports_a_row_that_cannot_be_decrypted_without_aborting_the_batch(
        self, monkeypatch
    ) -> None:
        key = Fernet.generate_key().decode("utf-8")
        monkeypatch.setenv("ENCRYPTION_KEY", key)
        tenant_id = make_tenant()
        good_id = make_connection(tenant_id, {"consumer_key": "ck"}, name="Good")
        corrupt_id = make_connection(tenant_id, {"consumer_key": "ck"}, name="Corrupt")

        async def _corrupt() -> None:
            async with async_session_factory() as db:
                connection = await db.get(Connection, corrupt_id)
                connection.encrypted_credentials = "not-valid-fernet-ciphertext"
                await db.commit()

        asyncio.run(_corrupt())

        result = reencrypt_all_connections.run()

        assert result["migrated"] == 1
        assert result["failed"] == [str(corrupt_id)]
        good_connection = _get_connection(good_id)
        assert decrypt_credentials(good_connection.encrypted_credentials, key=key) == {
            "consumer_key": "ck"
        }

    def test_skips_a_connection_with_no_credentials(self, monkeypatch) -> None:
        key = Fernet.generate_key().decode("utf-8")
        monkeypatch.setenv("ENCRYPTION_KEY", key)
        tenant_id = make_tenant()

        async def _create_without_credentials() -> uuid.UUID:
            from cp_domain.connection import ConnectionPlatform, ConnectionStatus

            async with async_session_factory() as db:
                connection = Connection(
                    tenant_id=tenant_id,
                    platform=ConnectionPlatform.WOOCOMMERCE,
                    name="No creds",
                    status=ConnectionStatus.CONNECTED,
                    encrypted_credentials=None,
                )
                db.add(connection)
                await db.commit()
                return connection.id

        asyncio.run(_create_without_credentials())

        result = reencrypt_all_connections.run()

        assert result == {"migrated": 0, "failed": []}
