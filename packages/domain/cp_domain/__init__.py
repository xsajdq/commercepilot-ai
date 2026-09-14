"""Importing this package registers every domain table on cp_shared's
Base.metadata - required by both Alembic autogenerate and any test that
needs the full schema created."""

from cp_domain.ai_job import AIJob, AIJobStatus
from cp_domain.approval import Approval, ApprovalStatus
from cp_domain.audit_event import ActorType, AuditEvent, AuditResult
from cp_domain.brand import Brand
from cp_domain.category import Category
from cp_domain.competitor_price import CompetitorPrice, CompetitorPriceSource
from cp_domain.connection import Connection, ConnectionPlatform, ConnectionStatus
from cp_domain.offer import Offer, OfferStatus
from cp_domain.order import Order, OrderItem, OrderStatus
from cp_domain.price import Price
from cp_domain.product import Product, ProductStatus
from cp_domain.recommendation import (
    Recommendation,
    RecommendationStatus,
    RecommendationType,
    RiskLevel,
)
from cp_domain.review import Review
from cp_domain.stock import Stock
from cp_domain.variant import Variant

__all__ = [
    "AIJob",
    "AIJobStatus",
    "ActorType",
    "Approval",
    "ApprovalStatus",
    "AuditEvent",
    "AuditResult",
    "Brand",
    "Category",
    "CompetitorPrice",
    "CompetitorPriceSource",
    "Connection",
    "ConnectionPlatform",
    "ConnectionStatus",
    "Offer",
    "OfferStatus",
    "Order",
    "OrderItem",
    "OrderStatus",
    "Price",
    "Product",
    "ProductStatus",
    "Recommendation",
    "RecommendationStatus",
    "RecommendationType",
    "Review",
    "RiskLevel",
    "Stock",
    "Variant",
]
