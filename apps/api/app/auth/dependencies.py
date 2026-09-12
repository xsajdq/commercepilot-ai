import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import get_membership
from app.core.security import InvalidTokenError, decode_access_token
from app.db.base import get_db
from app.db.models.membership import Membership, MembershipRole
from app.db.models.user import User

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

_credentials_error = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_claims(
    token: Annotated[str | None, Depends(_oauth2_scheme)],
) -> dict:
    if token is None:
        raise _credentials_error
    try:
        return decode_access_token(token)
    except InvalidTokenError as exc:
        raise _credentials_error from exc


async def get_current_user(
    claims: Annotated[dict, Depends(get_current_claims)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    user = await db.get(User, uuid.UUID(claims["sub"]))
    if user is None or not user.is_active:
        raise _credentials_error
    return user


async def get_current_membership(
    claims: Annotated[dict, Depends(get_current_claims)],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Membership:
    """The tenant middleware: the tenant_id used for every request comes
    only from this signed, server-issued token - never from a client
    header or query param - and is re-verified against the memberships
    table on every request so a revoked membership takes effect
    immediately, not just at the next login."""
    tenant_id = uuid.UUID(claims["tenant_id"])
    membership = await get_membership(db, user_id=user.id, tenant_id=tenant_id)
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No access to this tenant",
        )
    return membership


def require_role(*roles: MembershipRole):
    async def _checker(
        membership: Annotated[Membership, Depends(get_current_membership)],
    ) -> Membership:
        if membership.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role for this action",
            )
        return membership

    return _checker
