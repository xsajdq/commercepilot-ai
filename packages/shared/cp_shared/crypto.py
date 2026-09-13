import json
from typing import Any

from cryptography.fernet import Fernet


def encrypt_credentials(data: dict[str, Any], *, key: str) -> str:
    """Encrypts a connector credentials dict (API keys, OAuth tokens, ...)
    for storage in Connection.encrypted_credentials. Never store the
    plaintext dict directly - CLAUDE.md forbids plaintext credentials.

    `key` is a Fernet key (see `Fernet.generate_key()`), passed in
    explicitly rather than read from settings here: this module has no
    business knowing which app's config holds it - both apps/api
    (encrypting on connection setup) and apps/worker (decrypting to
    sync) need this with their own config wiring.
    """
    payload = json.dumps(data).encode("utf-8")
    return Fernet(key.encode("utf-8")).encrypt(payload).decode("utf-8")


def decrypt_credentials(token: str, *, key: str) -> dict[str, Any]:
    payload = Fernet(key.encode("utf-8")).decrypt(token.encode("utf-8"))
    return json.loads(payload)
