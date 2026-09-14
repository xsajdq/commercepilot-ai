import json
from typing import Any

from cryptography.fernet import Fernet, MultiFernet


def _multi_fernet(key: str | list[str]) -> MultiFernet:
    """A single key or a list works identically - `MultiFernet` always
    *encrypts* with the first key and *decrypts* by trying each key in
    order, exactly the primitive Fernet's own docs recommend for
    zero-downtime key rotation (Phase 21): pass `[new_key, old_key]`
    during a rotation window so new writes move to the new key while
    data written under the old one still decrypts.
    """
    keys = key if isinstance(key, list) else [key]
    return MultiFernet([Fernet(k.encode("utf-8")) for k in keys])


def encrypt_credentials(data: dict[str, Any], *, key: str | list[str]) -> str:
    """Encrypts a connector credentials dict (API keys, OAuth tokens, ...)
    for storage in Connection.encrypted_credentials. Never store the
    plaintext dict directly - CLAUDE.md forbids plaintext credentials.

    `key` is a Fernet key (see `Fernet.generate_key()`) or a list of
    them, passed in explicitly rather than read from settings here:
    this module has no business knowing which app's config holds it -
    both apps/api (encrypting on connection setup) and apps/worker
    (decrypting to sync) need this with their own config wiring. When a
    list is given, encryption always uses the first (current) key.
    """
    payload = json.dumps(data).encode("utf-8")
    return _multi_fernet(key).encrypt(payload).decode("utf-8")


def decrypt_credentials(token: str, *, key: str | list[str]) -> dict[str, Any]:
    payload = _multi_fernet(key).decrypt(token.encode("utf-8"))
    return json.loads(payload)
