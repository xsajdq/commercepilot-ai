import json
from typing import Any

from cryptography.fernet import Fernet

from app.core.config import get_settings


def _fernet() -> Fernet:
    return Fernet(get_settings().encryption_key.encode("utf-8"))


def encrypt_credentials(data: dict[str, Any]) -> str:
    """Encrypts a connector credentials dict (API keys, OAuth tokens, ...)
    for storage in Connection.encrypted_credentials. Never store the
    plaintext dict directly - CLAUDE.md forbids plaintext credentials."""
    payload = json.dumps(data).encode("utf-8")
    return _fernet().encrypt(payload).decode("utf-8")


def decrypt_credentials(token: str) -> dict[str, Any]:
    payload = _fernet().decrypt(token.encode("utf-8"))
    return json.loads(payload)
