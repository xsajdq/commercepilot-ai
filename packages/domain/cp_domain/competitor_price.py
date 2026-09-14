import enum
import uuid
from datetime import datetime
from decimal import Decimal

from cp_shared.db import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import DateTime, ForeignKey, Numeric, String, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column


class CompetitorPriceSource(str, enum.Enum):
    MANUAL = "manual"
    # A future phase's job, not this one's: a real price-comparison API
    # integration would write rows here with source=API - the schema and
    # the pricing agent's consumption of this table (Phase 14) are
    # already source-agnostic, so that's the only change it would need.
    API = "api"


class CompetitorPrice(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    """One observed competitor price for one of our products - Phase 14's
    missing link: `cp_pricing.compute_price_bounds` has accepted
    `competitor_prices` since Phase 9, but nothing ever populated it
    until this table existed."""

    __tablename__ = "competitor_prices"

    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    competitor_name: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="PLN")
    source: Mapped[CompetitorPriceSource] = mapped_column(
        SAEnum(CompetitorPriceSource, name="competitor_price_source"),
        nullable=False,
        default=CompetitorPriceSource.MANUAL,
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
