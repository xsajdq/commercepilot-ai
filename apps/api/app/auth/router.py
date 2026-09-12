from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import service
from app.auth.dependencies import get_current_membership, get_current_user
from app.auth.schemas import (
    LoginRequest,
    MembershipOut,
    MeResponse,
    RefreshRequest,
    RegisterRequest,
    SwitchTenantRequest,
    TenantMembershipsResponse,
    TokenResponse,
    UserOut,
)
from app.db.base import get_db
from app.db.models.membership import Membership
from app.db.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginResponse(BaseModel):
    requires_tenant_selection: bool
    token: TokenResponse | None = None
    memberships: list[MembershipOut] | None = None


def _to_token_response(
    access_token: str, refresh_token: str, membership: Membership
) -> TokenResponse:
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        tenant_id=membership.tenant_id,
        role=membership.role,
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register_endpoint(
    payload: RegisterRequest, db: Annotated[AsyncSession, Depends(get_db)]
) -> TokenResponse:
    try:
        access_token, refresh_token, membership = await service.register(
            db,
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
            tenant_name=payload.tenant_name,
        )
    except service.EmailAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        ) from exc

    return _to_token_response(access_token, refresh_token, membership)


@router.post("/login", response_model=LoginResponse)
async def login_endpoint(
    payload: LoginRequest, db: Annotated[AsyncSession, Depends(get_db)]
) -> LoginResponse:
    try:
        access_token, refresh_token, membership = await service.login(
            db, email=payload.email, password=payload.password, tenant_id=payload.tenant_id
        )
    except service.AmbiguousTenantError:
        user = await service.authenticate(db, email=payload.email, password=payload.password)
        memberships = await service.get_memberships(db, user.id)
        return LoginResponse(
            requires_tenant_selection=True,
            memberships=[MembershipOut.model_validate(m) for m in memberships],
        )
    except (service.InvalidCredentialsError, service.TenantAccessDeniedError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        ) from exc

    return LoginResponse(
        requires_tenant_selection=False,
        token=_to_token_response(access_token, refresh_token, membership),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_endpoint(
    payload: RefreshRequest, db: Annotated[AsyncSession, Depends(get_db)]
) -> TokenResponse:
    try:
        access_token, refresh_token, membership = await service.refresh_tokens(
            db, refresh_token=payload.refresh_token
        )
    except service.RefreshTokenInvalidError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        ) from exc

    return _to_token_response(access_token, refresh_token, membership)


@router.post("/switch-tenant", response_model=TokenResponse)
async def switch_tenant_endpoint(
    payload: SwitchTenantRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> TokenResponse:
    try:
        access_token, refresh_token, membership = await service.switch_tenant(
            db, user=user, tenant_id=payload.tenant_id
        )
    except service.TenantAccessDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="No access to this tenant"
        ) from exc

    return _to_token_response(access_token, refresh_token, membership)


@router.get("/tenants", response_model=TenantMembershipsResponse)
async def list_my_tenants(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> TenantMembershipsResponse:
    memberships = await service.get_memberships(db, user.id)
    return TenantMembershipsResponse(
        memberships=[MembershipOut.model_validate(m) for m in memberships]
    )


@router.get("/me", response_model=MeResponse)
async def me_endpoint(
    user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[Membership, Depends(get_current_membership)],
) -> MeResponse:
    return MeResponse(
        user=UserOut.model_validate(user),
        tenant=membership.tenant,
        role=membership.role,
    )
