from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from cp_connectors.exceptions import (
    ConnectorAuthError,
    ConnectorError,
    ConnectorNotFoundError,
    ConnectorRateLimitError,
)
from cp_connectors.types import (
    ConnectorCategory,
    ConnectorProduct,
    PriceUpdate,
    StockUpdate,
    UploadedImage,
)

_DEFAULT_TIMEOUT_SECONDS = 15.0


class WooCommerceConnector:
    """CommerceConnector for a WooCommerce store, via REST API v3
    (`/wp-json/wc/v3`). Only Consumer Key/Secret auth over HTTPS is
    supported - WooCommerce requires OAuth1.0a request signing for plain
    HTTP instead, which this class does not implement; connect stores
    over HTTPS.

    Retry/backoff/rate-limit handling is deliberately NOT done here -
    that's the sync engine's job (Phase 6). This class only makes the
    request and translates the response into typed results or typed
    exceptions the caller can act on.

    Each ConnectorProduct maps to one WooCommerce *simple* product.
    Variable products (per-variation price/stock) aren't modeled yet -
    extending this to variations is future work once the sync engine
    needs it. A product's categories are similarly simplified to just
    the first one WooCommerce returns.
    """

    def __init__(
        self,
        *,
        store_url: str,
        consumer_key: str,
        consumer_secret: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        base_url = store_url.rstrip("/") + "/wp-json/wc/v3"
        self._client = client or httpx.AsyncClient(
            base_url=base_url,
            params={"consumer_key": consumer_key, "consumer_secret": consumer_secret},
            timeout=_DEFAULT_TIMEOUT_SECONDS,
        )

    async def __aenter__(self) -> "WooCommerceConnector":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        response = await self._client.request(method, path, **kwargs)
        if response.status_code in (401, 403):
            raise ConnectorAuthError(f"WooCommerce rejected credentials: {response.text}")
        if response.status_code == 404:
            raise ConnectorNotFoundError(f"WooCommerce 404 for {method} {path}")
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            raise ConnectorRateLimitError(
                "WooCommerce rate limit hit",
                retry_after_seconds=float(retry_after) if retry_after else None,
            )
        if response.status_code >= 400:
            raise ConnectorError(
                f"WooCommerce {method} {path} failed with {response.status_code}: {response.text}"
            )
        return response

    @staticmethod
    def _to_connector_product(raw: dict[str, Any]) -> ConnectorProduct:
        categories = raw.get("categories") or []
        price_raw = raw.get("regular_price") or raw.get("price")
        try:
            price = Decimal(str(price_raw)) if price_raw not in (None, "") else None
        except InvalidOperation:
            price = None

        return ConnectorProduct(
            external_id=str(raw["id"]),
            sku=raw.get("sku") or "",
            name=raw.get("name") or "",
            description=raw.get("description") or None,
            price=price,
            stock_quantity=raw.get("stock_quantity"),
            category_external_id=str(categories[0]["id"]) if categories else None,
            image_urls=[img["src"] for img in raw.get("images") or [] if img.get("src")],
            status=raw.get("status") or "draft",
        )

    @staticmethod
    def _to_woocommerce_payload(product: ConnectorProduct) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "sku": product.sku,
            "name": product.name,
            "status": product.status,
        }
        if product.description is not None:
            payload["description"] = product.description
        if product.price is not None:
            payload["regular_price"] = str(product.price)
        if product.stock_quantity is not None:
            payload["manage_stock"] = True
            payload["stock_quantity"] = product.stock_quantity
        if product.category_external_id is not None:
            payload["categories"] = [{"id": int(product.category_external_id)}]
        if product.image_urls:
            payload["images"] = [{"src": url} for url in product.image_urls]
        return payload

    async def get_products(
        self, *, cursor: str | None = None, limit: int = 50
    ) -> tuple[list[ConnectorProduct], str | None]:
        page = int(cursor) if cursor else 1
        response = await self._request(
            "GET", "/products", params={"page": page, "per_page": limit}
        )
        products = [self._to_connector_product(raw) for raw in response.json()]

        total_pages_header = response.headers.get("X-WP-TotalPages")
        total_pages = int(total_pages_header) if total_pages_header else page
        next_cursor = str(page + 1) if page < total_pages else None
        return products, next_cursor

    async def get_product(self, external_id: str) -> ConnectorProduct:
        response = await self._request("GET", f"/products/{external_id}")
        return self._to_connector_product(response.json())

    async def create_product(self, product: ConnectorProduct) -> ConnectorProduct:
        response = await self._request(
            "POST", "/products", json=self._to_woocommerce_payload(product)
        )
        return self._to_connector_product(response.json())

    async def update_product(
        self, external_id: str, product: ConnectorProduct
    ) -> ConnectorProduct:
        response = await self._request(
            "PUT", f"/products/{external_id}", json=self._to_woocommerce_payload(product)
        )
        return self._to_connector_product(response.json())

    async def update_price(self, update: PriceUpdate) -> None:
        await self._request(
            "PUT",
            f"/products/{update.external_id}",
            json={"regular_price": str(update.price)},
        )

    async def update_stock(self, update: StockUpdate) -> None:
        await self._request(
            "PUT",
            f"/products/{update.external_id}",
            json={"manage_stock": True, "stock_quantity": update.quantity},
        )

    async def get_categories(self) -> list[ConnectorCategory]:
        response = await self._request("GET", "/products/categories", params={"per_page": 100})
        return [
            ConnectorCategory(
                external_id=str(raw["id"]),
                name=raw["name"],
                parent_external_id=str(raw["parent"]) if raw.get("parent") else None,
            )
            for raw in response.json()
        ]

    async def upload_image(self, external_id: str, image_url: str) -> UploadedImage:
        """WooCommerce has no standalone image-upload endpoint - it
        sideloads an image from a URL when that URL appears in a
        product's `images` array. This fetches the current list, appends
        the new one, and writes the product back."""
        current = await self.get_product(external_id)
        await self._request(
            "PUT",
            f"/products/{external_id}",
            json={"images": [{"src": url} for url in [*current.image_urls, image_url]]},
        )
        return UploadedImage(external_id=external_id, url=image_url)
