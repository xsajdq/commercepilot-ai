from typing import Protocol, runtime_checkable

from cp_connectors.types import (
    CategoryParameter,
    ConnectorCategory,
    ConnectorProduct,
    PriceUpdate,
    StockUpdate,
    UploadedImage,
)


@runtime_checkable
class CommerceConnector(Protocol):
    """Every platform integration (WooCommerce, Allegro, ...) implements
    this. Callers - the sync engine, AI tools - only ever see this
    interface, never a platform SDK, so an agent cannot know or care
    which platform it's talking to (CONTRIBUTING.md #16).

    Every method must be safe to retry: a network timeout followed by a
    retry must never double-create a product or double-apply a price
    change (CONTRIBUTING.md #11). Concrete implementations are responsible for
    that - e.g. by using the platform's own idempotency keys where
    available, or by checking-then-acting.
    """

    async def get_products(
        self, *, cursor: str | None = None, limit: int = 50
    ) -> tuple[list[ConnectorProduct], str | None]:
        """Returns a page of products and the cursor for the next page
        (None once this was the last page)."""
        ...

    async def get_product(self, external_id: str) -> ConnectorProduct:
        """Raises ConnectorNotFoundError if external_id doesn't exist."""
        ...

    async def create_product(self, product: ConnectorProduct) -> ConnectorProduct:
        """Returns the product with its platform-assigned external_id."""
        ...

    async def update_product(
        self, external_id: str, product: ConnectorProduct
    ) -> ConnectorProduct:
        """Raises ConnectorNotFoundError if external_id doesn't exist."""
        ...

    async def update_price(self, update: PriceUpdate) -> None:
        """Raises ConnectorNotFoundError if update.external_id doesn't exist."""
        ...

    async def update_stock(self, update: StockUpdate) -> None:
        """Raises ConnectorNotFoundError if update.external_id doesn't exist."""
        ...

    async def get_categories(self) -> list[ConnectorCategory]:
        ...

    async def upload_image(self, external_id: str, image_url: str) -> UploadedImage:
        """external_id is the product the image belongs to. Raises
        ConnectorNotFoundError if it doesn't exist."""
        ...

    async def get_category_parameters(self, category_external_id: str) -> list[CategoryParameter]:
        """Category-specific attributes required (or allowed) to list in
        this category - e.g. Allegro's per-category mandatory parameters
        (brand, size, ...), set via ConnectorProduct.parameters. Platforms
        without this concept (e.g. WooCommerce) return an empty list."""
        ...

    async def publish_offer(self, external_id: str) -> None:
        """Makes a previously-created draft listing live. Platforms where
        create_product already makes it live treat this as a no-op (or an
        explicit "ensure it's live" call); platforms with a distinct
        draft -> active step (e.g. Allegro) perform it here. Raises
        ConnectorNotFoundError if external_id doesn't exist."""
        ...
