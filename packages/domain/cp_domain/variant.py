import uuid
from decimal import Decimal

from cp_shared.db import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import ForeignKey, Numeric, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import UniqueConstraint


class Variant(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "variants"
    __table_args__ = (UniqueConstraint("tenant_id", "sku", name="uq_variant_tenant_sku"),)

    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    ean: Mapped[str | None] = mapped_column(String(32), nullable=True)
    name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    attributes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)

    product: Mapped["Product"] = relationship(back_populates="variants")  # noqa: F821
    offers: Mapped[list["Offer"]] = relationship(  # noqa: F821
        back_populates="variant", cascade="all, delete-orphan"
    )
