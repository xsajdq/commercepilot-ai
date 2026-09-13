from decimal import Decimal

from pydantic import BaseModel, Field


class ConnectorCategory(BaseModel):
    external_id: str
    name: str
    parent_external_id: str | None = None


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
