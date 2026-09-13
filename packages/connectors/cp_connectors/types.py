from decimal import Decimal

from pydantic import BaseModel, Field


class ConnectorCategory(BaseModel):
    external_id: str
    name: str
    parent_external_id: str | None = None


class CategoryParameter(BaseModel):
    """A category-specific attribute a marketplace requires (or allows)
    when listing in that category - e.g. Allegro's per-category mandatory
    parameters (brand, size, ...). Platforms without this concept (e.g.
    WooCommerce) never produce these."""

    external_id: str
    name: str
    required: bool
    # For a fixed-choice ("dictionary") parameter, the allowed values as
    # {"id": ..., "value": ...}; empty for a free-text/numeric parameter.
    dictionary_values: list[dict[str, str]] = Field(default_factory=list)


class ConnectorProduct(BaseModel):
    """What a connector reads from / writes to an external platform.

    Deliberately not cp_domain.Product: a connector never touches the
    database, and the domain model must never import a connector or
    platform SDK (CLAUDE.md #16). The sync engine (Phase 6) is what maps
    between this and the domain model.
    """

    external_id: str | None = None  # unset until the platform assigns one
    sku: str
    name: str
    description: str | None = None
    ean: str | None = None
    price: Decimal | None = None
    currency: str = "PLN"
    stock_quantity: int | None = None
    category_external_id: str | None = None
    image_urls: list[str] = Field(default_factory=list)
    status: str = "draft"
    # Category parameter values, e.g. Allegro's per-category mandatory
    # attributes: {parameter_external_id: [value_or_value_id, ...]}.
    # Platforms without this concept (e.g. WooCommerce) just ignore it.
    parameters: dict[str, list[str]] = Field(default_factory=dict)


class PriceUpdate(BaseModel):
    external_id: str
    price: Decimal
    currency: str = "PLN"


class StockUpdate(BaseModel):
    external_id: str
    quantity: int


class UploadedImage(BaseModel):
    external_id: str
    url: str
