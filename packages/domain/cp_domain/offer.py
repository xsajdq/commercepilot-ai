import enum
import uuid

from cp_shared.db import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import UniqueConstraint


class OfferStatus(str, enum.Enum):
    DRAFT = "draft"
    PENDING = "pending"
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"


class Offer(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    """A variant listed on one connection (store/marketplace account).
    Price and stock are channel-specific, so they hang off the offer, not
    the variant."""

    __tablename__ = "offers"
    __table_args__ = (
        UniqueConstraint("connection_id", "variant_id", name="uq_offer_connection_variant"),
    )

    connection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    variant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("variants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    external_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[OfferStatus] = mapped_column(
        SAEnum(OfferStatus, name="offer_status"), nullable=False, default=OfferStatus.DRAFT
    )

    connection: Mapped["Connection"] = relationship(back_populates="offers")  # noqa: F821
    variant: Mapped["Variant"] = relationship(back_populates="offers")  # noqa: F821
    price: Mapped["Price | None"] = relationship(  # noqa: F821
        back_populates="offer", uselist=False, cascade="all, delete-orphan"
    )
    stock: Mapped["Stock | None"] = relationship(  # noqa: F821
        back_populates="offer", uselist=False, cascade="all, delete-orphan"
    )
