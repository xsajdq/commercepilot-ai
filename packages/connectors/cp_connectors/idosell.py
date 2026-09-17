from typing import Any

import httpx

from cp_connectors.exceptions import (
    ConnectorAuthError,
    ConnectorError,
    ConnectorNotFoundError,
    ConnectorRateLimitError,
)
from cp_connectors.types import (
    CategoryParameter,
    ConnectorCategory,
    ConnectorProduct,
    PriceUpdate,
    StockUpdate,
    UploadedImage,
)

_DEFAULT_TIMEOUT_SECONDS = 15.0

_WRITE_NOT_IMPLEMENTED = (
    "IdoSellConnector does not implement {method} - its request/response schema could "
    "not be confirmed from any source reachable in the environment this was built in "
    "(developers.idosell.com, idosell.readme.io, and idosell.com were all network-"
    "blocked). Per CONTRIBUTING.md #9 ('never invent product technical specifications'), this "
    "connector will not guess a mutating payload that could silently corrupt a real "
    "store's inventory or pricing. Confirm the real request/response shape against "
    "IdoSell's own docs or a real store before implementing this method."
)


class IdoSellConnector:
    """CommerceConnector for an IdoSell store, via IdoSell's Admin API v3
    (`{store_url}/api/admin/v3`).

    Deliberately incomplete - the roadmap itself calls for "own research
    first, don't force the WooCommerce-shaped abstraction" for this
    platform, and IdoSell's official documentation
    (idosell.com/developers, idosell.readme.io) was network-blocked in
    the environment this was built in. Rather than guess field names
    CONTRIBUTING.md #9 forbids inventing, this class draws a hard line between
    what could actually be confirmed (via search-engine-indexed
    fragments of IdoSell's own docs and blog posts) and everything else:

    Confirmed:
    - Auth: an `X-API-KEY` request header carrying a key generated in
      the IdoSell admin panel (Administration -> API -> Access Keys).
    - Base URL: `{store_url}/api/admin/v3`.
    - Pagination: `result_page` (1-based) / `result_limit` query
      params, capped at 100 items per page by the platform.
    - One confirmed full example URL:
      `GET /products/categories?ids=...&languages=pol,eng&result_page=1&result_limit=10`.
    - One confirmed product field name: `productId`.

    NOT confirmed - and NOT guessed:
    - The exact products list/detail endpoint path (this class follows
      the same `products/<resource>` naming convention the confirmed
      categories URL uses, as its best-effort guess - flagged here as
      inference, not fact).
    - Every other product/category field name (sku, name, price,
      description, stock, parent category, image shape). IdoSell also
      models stock per product *size*/variant rather than one flat
      quantity (the roadmap's own reason to research this platform
      separately) - a confirmed field name wouldn't even map cleanly
      onto `ConnectorProduct.stock_quantity` without further research.
    - The exact success/list-envelope shape of a JSON response.

    Given that, this connector's methods split into two tiers:

    - **Reads** (`get_products`, `get_product`, `get_categories`) make
      the real, confirmed-shape HTTP call (real auth header, real base
      URL, real pagination) and parse only the one confirmed field
      (`productId`/`id`) plus a generic "first list found in the
      response body" envelope-detection heuristic (not a guessed key
      name - a defensive fallback that works whatever the real envelope
      key turns out to be). Every other `ConnectorProduct`/
      `ConnectorCategory` field is left at its honest "unknown" default
      (`""`/`None`) rather than mapped from a guessed key - a caller
      gets a real count and real ids, nothing invented.
    - **Writes** (`create_product`, `update_product`, `update_price`,
      `update_stock`, `upload_image`, `publish_offer`) all raise
      `ConnectorError` immediately: a wrong guess here would mean
      writing a fabricated payload to a real store's real inventory or
      pricing, which is a materially worse failure mode than a blank
      read field. `get_category_parameters` returns `[]` (safe - no
      concept to guess at).

    Retry/backoff/rate-limit handling is deliberately NOT done here -
    that's the sync engine's job (Phase 6).
    """

    def __init__(
        self,
        *,
        store_url: str,
        api_key: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(
            base_url=store_url.rstrip("/") + "/api/admin/v3",
            headers={"X-API-KEY": api_key},
            timeout=_DEFAULT_TIMEOUT_SECONDS,
        )

    async def __aenter__(self) -> "IdoSellConnector":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        response = await self._client.request(method, path, **kwargs)
        if response.status_code in (401, 403):
            raise ConnectorAuthError(f"IdoSell rejected the API key: {response.text}")
        if response.status_code == 404:
            raise ConnectorNotFoundError(f"IdoSell 404 for {method} {path}")
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            raise ConnectorRateLimitError(
                "IdoSell rate limit hit",
                retry_after_seconds=float(retry_after) if retry_after else None,
            )
        if response.status_code >= 400:
            raise ConnectorError(
                f"IdoSell {method} {path} failed with {response.status_code}: {response.text}"
            )
        return response

    @staticmethod
    def _first_list_in(body: Any) -> list[dict[str, Any]]:
        """The real list-envelope key was never confirmed - rather than
        guess one, return the first list of dicts found anywhere in the
        response body, whatever it's actually called."""
        if isinstance(body, list):
            return [item for item in body if isinstance(item, dict)]
        if isinstance(body, dict):
            for value in body.values():
                if isinstance(value, list) and (not value or isinstance(value[0], dict)):
                    return value
        return []

    def _to_connector_product(self, raw: dict[str, Any]) -> ConnectorProduct:
        external_id = raw.get("productId", raw.get("id"))
        return ConnectorProduct(
            external_id=str(external_id) if external_id is not None else None,
            sku="",
            name="",
            status="draft",
        )

    async def get_products(
        self, *, cursor: str | None = None, limit: int = 50
    ) -> tuple[list[ConnectorProduct], str | None]:
        page = int(cursor) if cursor else 1
        response = await self._request(
            "GET",
            "/products/products/search",
            params={"result_page": page, "result_limit": limit},
        )
        raw_products = self._first_list_in(response.json())
        products = [self._to_connector_product(raw) for raw in raw_products]
        next_cursor = str(page + 1) if len(raw_products) == limit else None
        return products, next_cursor

    async def get_product(self, external_id: str) -> ConnectorProduct:
        response = await self._request(
            "GET", "/products/products/search", params={"ids": external_id}
        )
        raw_products = self._first_list_in(response.json())
        if not raw_products:
            raise ConnectorNotFoundError(f"IdoSell product {external_id} not found")
        return self._to_connector_product(raw_products[0])

    async def create_product(self, product: ConnectorProduct) -> ConnectorProduct:
        raise ConnectorError(_WRITE_NOT_IMPLEMENTED.format(method="create_product"))

    async def update_product(
        self, external_id: str, product: ConnectorProduct
    ) -> ConnectorProduct:
        raise ConnectorError(_WRITE_NOT_IMPLEMENTED.format(method="update_product"))

    async def update_price(self, update: PriceUpdate) -> None:
        raise ConnectorError(_WRITE_NOT_IMPLEMENTED.format(method="update_price"))

    async def update_stock(self, update: StockUpdate) -> None:
        raise ConnectorError(_WRITE_NOT_IMPLEMENTED.format(method="update_stock"))

    async def get_categories(self) -> list[ConnectorCategory]:
        response = await self._request(
            "GET",
            "/products/categories",
            params={"languages": "pol,eng", "result_page": 1, "result_limit": 100},
        )
        categories = []
        for raw in self._first_list_in(response.json()):
            category_id = raw.get("categoryId", raw.get("id"))
            if category_id is None:
                continue
            categories.append(
                ConnectorCategory(external_id=str(category_id), name="", parent_external_id=None)
            )
        return categories

    async def upload_image(self, external_id: str, image_url: str) -> UploadedImage:
        raise ConnectorError(_WRITE_NOT_IMPLEMENTED.format(method="upload_image"))

    async def get_category_parameters(self, category_external_id: str) -> list[CategoryParameter]:
        """No per-category mandatory-parameter concept was found - always
        empty, same as WooCommerce/Shoper/PrestaShop. Unlike those, this
        isn't just "nothing found" - it's "not researched", but the safe
        answer is identical either way."""
        return []

    async def publish_offer(self, external_id: str) -> None:
        raise ConnectorError(_WRITE_NOT_IMPLEMENTED.format(method="publish_offer"))
