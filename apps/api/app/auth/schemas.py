import uuid

from pydantic import BaseModel, EmailStr, Field

from app.db.models.membership import MembershipRole


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)
    tenant_name: str = Field(min_length=1, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    tenant_id: uuid.UUID | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class SwitchTenantRequest(BaseModel):
    tenant_id: uuid.UUID


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    tenant_id: uuid.UUID
    role: MembershipRole


class UserOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str

    model_config = {"from_attributes": True}


class TenantOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str

    model_config = {"from_attributes": True}


class MembershipOut(BaseModel):
    tenant: TenantOut
    role: MembershipRole

    model_config = {"from_attributes": True}


class MeResponse(BaseModel):
    user: UserOut
    tenant: TenantOut
    role: MembershipRole


class TenantMembershipsResponse(BaseModel):
    memberships: list[MembershipOut]
