import uuid

from cp_shared.db import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import ForeignKey, Integer, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Stock(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    """Current stock level for one offer."""

    __tablename__ = "stocks"

    offer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("offers.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    offer: Mapped["Offer"] = relationship(back_populates="stock")  # noqa: F821
