import re
import secrets
import uuid
from datetime import UTC, datetime

from cp_domain.subscription import Subscription
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    refresh_token_expiry,
    verify_password,
)
from app.db.models.membership import Membership, MembershipRole
from app.db.models.refresh_token import RefreshToken
from app.db.models.tenant import Tenant
from app.db.models.user import User


class EmailAlreadyExistsError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class TenantAccessDeniedError(Exception):
    pass


class AmbiguousTenantError(Exception):
    """Raised at login when the user belongs to multiple tenants and did
    not specify which one to authenticate into."""


class RefreshTokenInvalidError(Exception):
    pass


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "tenant"


async def _unique_slug(db: AsyncSession, name: str) -> str:
    base = _slugify(name)
    slug = base
    while await db.scalar(select(Tenant).where(Tenant.slug == slug)) is not None:
        slug = f"{base}-{secrets.token_hex(3)}"
    return slug


async def register(
    db: AsyncSession, *, email: str, password: str, full_name: str, tenant_name: str
) -> tuple[str, str, Membership]:
    email = email.lower()
    existing = await db.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise EmailAlreadyExistsError(email)

    tenant = Tenant(name=tenant_name, slug=await _unique_slug(db, tenant_name))
    user = User(email=email, hashed_password=hash_password(password), full_name=full_name)
    db.add_all([tenant, user])
    await db.flush()

    membership = Membership(user_id=user.id, tenant_id=tenant.id, role=MembershipRole.OWNER)
    db.add(membership)
    # Every tenant has exactly one Subscription from the moment it
    # exists (Phase 20) - defaults to the free plan, never a nullable
    # "no subscription yet" case callers have to special-case.
    db.add(Subscription(tenant_id=tenant.id))
    membership.tenant = tenant
    membership.user = user

    access_token, refresh_token = await _issue_token_pair(db, user=user, membership=membership)
    return access_token, refresh_token, membership


async def authenticate(db: AsyncSession, *, email: str, password: str) -> User:
    user = await db.scalar(select(User).where(User.email == email.lower()))
    if user is None or not user.is_active or not verify_password(password, user.hashed_password):
        raise InvalidCredentialsError()
    return user


async def get_memberships(db: AsyncSession, user_id: uuid.UUID) -> list[Membership]:
    result = await db.scalars(
        select(Membership)
        .where(Membership.user_id == user_id)
        .options(selectinload(Membership.tenant))
    )
    return list(result)


async def get_membership(
    db: AsyncSession, *, user_id: uuid.UUID, tenant_id: uuid.UUID
) -> Membership | None:
    return await db.scalar(
        select(Membership)
        .where(Membership.user_id == user_id, Membership.tenant_id == tenant_id)
        .options(selectinload(Membership.tenant))
    )


async def _issue_token_pair(
    db: AsyncSession, *, user: User, membership: Membership
) -> tuple[str, str]:
    access_token = create_access_token(
        user_id=user.id, tenant_id=membership.tenant_id, role=membership.role
    )
    refresh_plain = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            tenant_id=membership.tenant_id,
            token_hash=hash_refresh_token(refresh_plain),
            expires_at=refresh_token_expiry(),
        )
    )
    await db.commit()
    return access_token, refresh_plain


async def login(
    db: AsyncSession, *, email: str, password: str, tenant_id: uuid.UUID | None
) -> tuple[str, str, Membership]:
    user = await authenticate(db, email=email, password=password)
    memberships = await get_memberships(db, user.id)

    if not memberships:
        raise TenantAccessDeniedError("user has no tenant memberships")

    if tenant_id is not None:
        membership = next((m for m in memberships if m.tenant_id == tenant_id), None)
        if membership is None:
            raise TenantAccessDeniedError(str(tenant_id))
    elif len(memberships) == 1:
        membership = memberships[0]
    else:
        raise AmbiguousTenantError()

    access_token, refresh_token = await _issue_token_pair(db, user=user, membership=membership)
    return access_token, refresh_token, membership


async def switch_tenant(
    db: AsyncSession, *, user: User, tenant_id: uuid.UUID
) -> tuple[str, str, Membership]:
    membership = await get_membership(db, user_id=user.id, tenant_id=tenant_id)
    if membership is None:
        raise TenantAccessDeniedError(str(tenant_id))
    access_token, refresh_token = await _issue_token_pair(db, user=user, membership=membership)
    return access_token, refresh_token, membership


async def refresh_tokens(db: AsyncSession, *, refresh_token: str) -> tuple[str, str, Membership]:
    token_hash = hash_refresh_token(refresh_token)
    stored = await db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))

    now = datetime.now(UTC)
    if stored is None or stored.revoked_at is not None or stored.expires_at < now:
        raise RefreshTokenInvalidError()

    # Single-use: rotating a refresh token immediately revokes the old one.
    stored.revoked_at = now

    user = await db.get(User, stored.user_id)
    membership = await get_membership(db, user_id=stored.user_id, tenant_id=stored.tenant_id)
    if user is None or not user.is_active or membership is None:
        await db.commit()
        raise RefreshTokenInvalidError()

    access_token, new_refresh_token = await _issue_token_pair(db, user=user, membership=membership)
    return access_token, new_refresh_token, membership
