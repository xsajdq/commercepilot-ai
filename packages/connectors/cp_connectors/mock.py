import itertools
from copy import deepcopy

from cp_connectors.base import CommerceConnector
from cp_connectors.exceptions import ConnectorNotFoundError
from cp_connectors.types import (
    CategoryParameter,
    ConnectorCategory,
    ConnectorProduct,
    PriceUpdate,
    StockUpdate,
    UploadedImage,
)


class MockConnector(CommerceConnector):
    """An in-memory fake implementing CommerceConnector - no network
    calls, no real store. Lets the sync engine, AI tools, and this
    package's own tests exercise the connector interface end to end
    before any real platform (WooCommerce, Allegro, ...) exists."""

    def __init__(
        self,
        *,
        categories: list[ConnectorCategory] | None = None,
        category_parameters: dict[str, list[CategoryParameter]] | None = None,
    ) -> None:
        self._products: dict[str, ConnectorProduct] = {}
        self._categories = categories or []
        self._category_parameters = category_parameters or {}
        self._id_counter = itertools.count(1)

    async def get_products(
        self, *, cursor: str | None = None, limit: int = 50
    ) -> tuple[list[ConnectorProduct], str | None]:
        ids = sorted(self._products)
        start = int(cursor) if cursor else 0
        page_ids = ids[start : start + limit]
        next_cursor = str(start + limit) if start + limit < len(ids) else None
        return [deepcopy(self._products[i]) for i in page_ids], next_cursor

    async def get_product(self, external_id: str) -> ConnectorProduct:
        try:
            return deepcopy(self._products[external_id])
        except KeyError:
            raise ConnectorNotFoundError(f"no product {external_id!r}") from None

    async def create_product(self, product: ConnectorProduct) -> ConnectorProduct:
        external_id = product.external_id or f"mock-{next(self._id_counter)}"
        stored = product.model_copy(update={"external_id": external_id})
        self._products[external_id] = stored
        return deepcopy(stored)

    async def update_product(
        self, external_id: str, product: ConnectorProduct
    ) -> ConnectorProduct:
        self._require_existing(external_id)
        stored = product.model_copy(update={"external_id": external_id})
        self._products[external_id] = stored
        return deepcopy(stored)

    async def update_price(self, update: PriceUpdate) -> None:
        self._require_existing(update.external_id)
        self._products[update.external_id] = self._products[update.external_id].model_copy(
            update={"price": update.price, "currency": update.currency}
        )

    async def update_stock(self, update: StockUpdate) -> None:
        self._require_existing(update.external_id)
        self._products[update.external_id] = self._products[update.external_id].model_copy(
            update={"stock_quantity": update.quantity}
        )

    async def get_categories(self) -> list[ConnectorCategory]:
        return deepcopy(self._categories)

    async def upload_image(self, external_id: str, image_url: str) -> UploadedImage:
        self._require_existing(external_id)
        product = self._products[external_id]
        self._products[external_id] = product.model_copy(
            update={"image_urls": [*product.image_urls, image_url]}
        )
        return UploadedImage(external_id=external_id, url=image_url)

    async def get_category_parameters(self, category_external_id: str) -> list[CategoryParameter]:
        return deepcopy(self._category_parameters.get(category_external_id, []))

    async def publish_offer(self, external_id: str) -> None:
        self._require_existing(external_id)
        product = self._products[external_id]
        self._products[external_id] = product.model_copy(update={"status": "active"})

    def _require_existing(self, external_id: str) -> None:
        if external_id not in self._products:
            raise ConnectorNotFoundError(f"no product {external_id!r}")
