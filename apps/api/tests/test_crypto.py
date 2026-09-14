from cryptography.fernet import Fernet

from app.core.config import get_settings
from app.core.crypto import decrypt_credentials, encrypt_credentials


def test_round_trip() -> None:
    data = {"consumer_key": "ck_abc123", "consumer_secret": "cs_xyz789"}
    token = encrypt_credentials(data)
    assert decrypt_credentials(token) == data


def test_ciphertext_never_contains_plaintext_secrets() -> None:
    data = {"api_key": "super-secret-value-do-not-leak"}
    token = encrypt_credentials(data)
    assert "super-secret-value-do-not-leak" not in token


def test_encrypting_the_same_data_twice_yields_different_ciphertext() -> None:
    """Fernet includes a random IV, so credentials rotation/rewriting
    doesn't produce a predictable, comparable ciphertext."""
    data = {"token": "same-value"}
    assert encrypt_credentials(data) != encrypt_credentials(data)


class TestEncryptionKeyRotation:
    """Phase 21: `encryption_key_previous` lets a `Connection` row
    written under the OLD key keep decrypting during a rotation window -
    see `Settings.encryption_keys`'s own docstring."""

    def test_data_written_before_rotation_still_decrypts_after(self, monkeypatch) -> None:
        settings = get_settings()
        old_key = settings.encryption_key
        data = {"consumer_key": "written-before-rotation"}
        token = encrypt_credentials(data)

        monkeypatch.setattr(settings, "encryption_key", Fernet.generate_key().decode("utf-8"))
        monkeypatch.setattr(settings, "encryption_key_previous", old_key)

        assert decrypt_credentials(token) == data

    def test_new_writes_after_rotation_use_only_the_new_key(self, monkeypatch) -> None:
        settings = get_settings()
        old_key = settings.encryption_key
        new_key = Fernet.generate_key().decode("utf-8")
        monkeypatch.setattr(settings, "encryption_key", new_key)
        monkeypatch.setattr(settings, "encryption_key_previous", old_key)

        token = encrypt_credentials({"token": "written-after-rotation"})

        # Once the rotation window closes (previous key removed), a
        # freshly written row must still decrypt.
        monkeypatch.setattr(settings, "encryption_key_previous", None)
        assert decrypt_credentials(token) == {"token": "written-after-rotation"}
