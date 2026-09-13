from typing import Any

from cp_shared.crypto import decrypt_credentials as _decrypt_credentials
from cp_shared.crypto import encrypt_credentials as _encrypt_credentials

from app.core.config import get_settings


def encrypt_credentials(data: dict[str, Any]) -> str:
    return _encrypt_credentials(data, key=get_settings().encryption_key)


def decrypt_credentials(token: str) -> dict[str, Any]:
    return _decrypt_credentials(token, key=get_settings().encryption_key)
