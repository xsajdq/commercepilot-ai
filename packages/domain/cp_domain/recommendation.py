import enum
import uuid
from decimal import Decimal

from cp_shared.db import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import Enum as SAEnum
from sqlalchemy import Numeric, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship


class RecommendationType(str, enum.Enum):
    PRICE_CHANGE = "price_change"
    CONTENT_UPDATE = "content_update"
    CATALOG_FIX = "catalog_fix"
    STOCK_ALERT = "stock_alert"
    LISTING_PUBLISH = "listing_publish"
    OTHER = "other"


class RiskLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RecommendationStatus(str, enum.Enum):
    PROPOSED = "proposed"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"
    SUCCESS = "success"
    FAILED = "failed"


class Recommendation(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    """AI-proposed action awaiting (or having gone through) human
    approval. entity_type/entity_id point at whatever it's about (a
    Product, an Offer, ...) - kept polymorphic and FK-free since a single
    recommendation type list will eventually span most domain tables."""

    __tablename__ = "recommendations"

    type: Mapped[RecommendationType] = mapped_column(
        SAEnum(RecommendationType, name="recommendation_type"), nullable=False
    )
    risk_level: Mapped[RiskLevel] = mapped_column(
        SAEnum(RiskLevel, name="risk_level"), nullable=False
    )
    status: Mapped[RecommendationStatus] = mapped_column(
        SAEnum(RecommendationStatus, name="recommendation_status"),
        nullable=False,
        default=RecommendationStatus.PROPOSED,
    )
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)

    approval: Mapped["Approval | None"] = relationship(  # noqa: F821
        back_populates="recommendation", uselist=False, cascade="all, delete-orphan"
    )
