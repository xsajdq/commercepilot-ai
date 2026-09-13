import enum
import uuid
from decimal import Decimal

from cp_shared.db import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Numeric, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import UniqueConstraint


class ProductStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class Product(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("tenant_id", "sku", name="uq_product_tenant_sku"),)

    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    # Unknown, not guessed: per CLAUDE.md, missing manufacturer data (ean,
    # cost, vat_rate, weight_kg, dimensions_cm) stays NULL rather than
    # having an agent invent a plausible-looking value.
    ean: Mapped[str | None] = mapped_column(String(32), nullable=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("brands.id", ondelete="SET NULL"), nullable=True
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    vat_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    dimensions_cm: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[ProductStatus] = mapped_column(
        SAEnum(ProductStatus, name="product_status"), nullable=False, default=ProductStatus.DRAFT
    )
    extra_attributes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    variants: Mapped[list["Variant"]] = relationship(  # noqa: F821
        back_populates="product", cascade="all, delete-orphan"
    )
