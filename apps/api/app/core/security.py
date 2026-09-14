import secrets
import uuid
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings
from app.db.models.membership import MembershipRole

# bcrypt truncates its input at 72 bytes; encoding to UTF-8 first (rather
# than relying on str.encode's default) keeps that limit meaningful for
# multi-byte characters too.
_MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")[:_MAX_PASSWORD_BYTES]
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    encoded = plain_password.encode("utf-8")[:_MAX_PASSWORD_BYTES]
    return bcrypt.checkpw(encoded, hashed_password.encode("utf-8"))


class InvalidTokenError(Exception):
    pass


def create_access_token(
    *, user_id: uuid.UUID, tenant_id: uuid.UUID, role: MembershipRole
) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": role.value,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Tries every currently-valid verification key in turn (see
    `Settings.jwt_verification_keys` and `secret_key_previous`'s own
    docstring) - a token signed under a key that has since become
    "previous" during a rotation still verifies until it naturally
    expires, rather than every logged-in user being force-logged-out
    the moment `secret_key` rotates."""
    settings = get_settings()
    last_error: JWTError | None = None
    payload: dict[str, Any] | None = None

    for key in settings.jwt_verification_keys:
        try:
            payload = jwt.decode(token, key, algorithms=[settings.jwt_algorithm])
            break
        except JWTError as exc:
            last_error = exc

    if payload is None:
        raise InvalidTokenError(str(last_error))

    if payload.get("type") != "access":
        raise InvalidTokenError("not an access token")

    return payload


def generate_refresh_token() -> str:
    """An opaque, high-entropy token - never a JWT. Only its hash is
    persisted, so the plaintext value exists solely in the client's hands
    and this one response; it cannot be recovered from the database."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def refresh_token_expiry() -> datetime:
    settings = get_settings()
    return datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
