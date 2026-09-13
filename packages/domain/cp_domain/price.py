import uuid
from decimal import Decimal

from cp_shared.db import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import ForeignKey, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Price(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    """Current price for one offer. Change history lives in AuditEvent
    (written by the approval engine, Phase 8), not duplicated here."""

    __tablename__ = "prices"

    offer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("offers.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="PLN")
    compare_at_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    offer: Mapped["Offer"] = relationship(back_populates="price")  # noqa: F821
