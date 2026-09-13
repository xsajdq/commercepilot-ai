from cp_shared.db import Base, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Tenant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False, index=True)

    memberships: Mapped[list["Membership"]] = relationship(  # noqa: F821
        back_populates="tenant", cascade="all, delete-orphan"
    )
