import enum
import uuid

from cp_shared.db import Base, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import Enum, ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import UniqueConstraint

from app.db.models.tenant import Tenant
from app.db.models.user import User


class MembershipRole(str, enum.Enum):
    OWNER = "owner"
    MANAGER = "manager"
    OPERATOR = "operator"
    VIEWER = "viewer"


class Membership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A user's role within one tenant. A user may belong to multiple
    tenants, each with an independent role - never assume a global role."""

    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "tenant_id", name="uq_membership_user_tenant"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[MembershipRole] = mapped_column(
        Enum(MembershipRole, name="membership_role"), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="memberships")
    tenant: Mapped[Tenant] = relationship(back_populates="memberships")
