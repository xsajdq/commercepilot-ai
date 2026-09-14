import time
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
    CategoryParameter,
    ConnectorCategory,
    ConnectorProduct,
    PriceUpdate,
    StockUpdate,
    UploadedImage,
)

_DEFAULT_TIMEOUT_SECONDS = 15.0
_DEFAULT_LOCALE = "pl_PL"
# A cached token is treated as expired this many seconds before its real
# expiry, so a request never starts with a token that dies mid-flight.
_TOKEN_EXPIRY_SAFETY_MARGIN_SECONDS = 30


class ShoperConnector:
    """CommerceConnector for a Shoper store, via Shoper's REST API
    (`{store_url}/webapi/rest`).

    Network access to developers.shoper.pl itself was blocked in this
    sandbox, so this was built from Shoper's own indexed API reference
    pages plus a third-party client library's resource names, not by
    reading the OpenAPI spec directly - confirmed vs. inferred details:

    Confirmed:
    - Auth: `POST /webapi/rest/auth` with HTTP Basic (client_id,
      client_secret) returns a bearer `access_token` (~30 day expiry, no
      refresh token). This class performs that exchange itself and
      re-authenticates transparently whenever the cached token is
      missing/expired or a request comes back 401 - a caller only ever
      supplies client_id/client_secret (the same shape as WooCommerce's
      consumer key/secret), never a token directly.
    - List endpoints return an envelope: `{count, pages, page, list}`.
    - A product has `code` (sku), `category_id`, a nested `stock` object
      (`{price, stock, availability_id, delivery_id}`), and a
      `translations` dict keyed by locale (e.g. `"pl_PL"`) holding
      `{name, description, active}`.

    Inferred (verify against a real store before relying on in
    production):
    - The product id field is `product_id` (every other id field found -
      `category_id`, `availability_id`, `delivery_id` - follows this
      `<noun>_id` convention).
    - Image upload is a separate `product-images` resource (its exact
      request shape wasn't confirmed) rather than an inline array on the
      product itself, unlike WooCommerce.

    Not implemented, same as WooCommerceConnector: no per-category
    mandatory-parameter concept was found, so get_category_parameters
    always returns [].

    `update_price`/`update_stock`/`publish_offer` read-then-write the
    relevant nested object (`stock`, or `translations[locale]`) instead
    of PUTting a bare partial fragment: price/stock_quantity share one
    `stock` object and name/description/active share one
    `translations[locale]` object, so a partial PUT of just the changed
    field risks the API treating that nested object as a full replace
    and silently dropping its siblings - unlike WooCommerce/Allegro
    where every mutable field already lives at its own top-level key.

    Retry/backoff/rate-limit handling is deliberately NOT done here -
    that's the sync engine's job (Phase 6).
    """

    def __init__(
        self,
        *,
        store_url: str,
        client_id: str,
        client_secret: str,
        locale: str = _DEFAULT_LOCALE,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._locale = locale
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0
        self._client = client or httpx.AsyncClient(
            base_url=store_url.rstrip("/") + "/webapi/rest",
            timeout=_DEFAULT_TIMEOUT_SECONDS,
        )

    async def __aenter__(self) -> "ShoperConnector":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _authenticate(self) -> None:
        response = await self._client.post(
            "/auth", auth=(self._client_id, self._client_secret)
        )
        if response.status_code in (401, 403):
            raise ConnectorAuthError(f"Shoper rejected credentials: {response.text}")
        if response.status_code >= 400:
            raise ConnectorError(
                f"Shoper auth request failed with {response.status_code}: {response.text}"
            )
        body = response.json()
        self._access_token = body["access_token"]
        expires_in = float(body.get("expires_in", 0))
        self._token_expires_at = time.monotonic() + max(
            0.0, expires_in - _TOKEN_EXPIRY_SAFETY_MARGIN_SECONDS
        )

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        if self._access_token is None or time.monotonic() >= self._token_expires_at:
            await self._authenticate()

        headers = {"Authorization": f"Bearer {self._access_token}"}
        response = await self._client.request(method, path, headers=headers, **kwargs)

        if response.status_code == 401:
            # The cached token may have been revoked server-side earlier
            # than its stated expires_in - re-authenticate exactly once
            # and retry, rather than surfacing a spurious auth failure
            # for what a fresh token would have handled fine.
            await self._authenticate()
            headers = {"Authorization": f"Bearer {self._access_token}"}
            response = await self._client.request(method, path, headers=headers, **kwargs)

        if response.status_code in (401, 403):
            raise ConnectorAuthError(f"Shoper rejected the access token: {response.text}")
        if response.status_code == 404:
            raise ConnectorNotFoundError(f"Shoper 404 for {method} {path}")
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            raise ConnectorRateLimitError(
                "Shoper rate limit hit",
                retry_after_seconds=float(retry_after) if retry_after else None,
            )
        if response.status_code >= 400:
            raise ConnectorError(
                f"Shoper {method} {path} failed with {response.status_code}: {response.text}"
            )
        return response

    def _translation(self, raw: dict[str, Any]) -> dict[str, Any]:
        return (raw.get("translations") or {}).get(self._locale) or {}

    def _to_connector_product(self, raw: dict[str, Any]) -> ConnectorProduct:
        stock = raw.get("stock") or {}
        translation = self._translation(raw)
        price_raw = stock.get("price")
        try:
            price = Decimal(str(price_raw)) if price_raw not in (None, "") else None
        except InvalidOperation:
            price = None

        return ConnectorProduct(
            external_id=str(raw["product_id"]),
            sku=raw.get("code") or "",
            name=translation.get("name") or "",
            description=translation.get("description") or None,
            price=price,
            stock_quantity=stock.get("stock"),
            category_external_id=str(raw["category_id"]) if raw.get("category_id") else None,
            status="active" if translation.get("active") else "draft",
        )

    def _to_shoper_payload(self, product: ConnectorProduct) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": product.sku,
            "translations": {
                self._locale: {
                    "name": product.name,
                    "description": product.description or "",
                    "active": 1 if product.status == "active" else 0,
                }
            },
        }
        if product.category_external_id is not None:
            payload["category_id"] = int(product.category_external_id)
        stock: dict[str, Any] = {}
        if product.price is not None:
            stock["price"] = str(product.price)
        if product.stock_quantity is not None:
            stock["stock"] = product.stock_quantity
        if stock:
            payload["stock"] = stock
        return payload

    async def get_products(
        self, *, cursor: str | None = None, limit: int = 50
    ) -> tuple[list[ConnectorProduct], str | None]:
        page = int(cursor) if cursor else 1
        response = await self._request(
            "GET", "/products", params={"page": page, "limit": limit}
        )
        body = response.json()
        products = [self._to_connector_product(raw) for raw in body.get("list", [])]
        pages = int(body.get("pages", page))
        next_cursor = str(page + 1) if page < pages else None
        return products, next_cursor

    async def get_product(self, external_id: str) -> ConnectorProduct:
        response = await self._request("GET", f"/products/{external_id}")
        return self._to_connector_product(response.json())

    async def create_product(self, product: ConnectorProduct) -> ConnectorProduct:
        response = await self._request(
            "POST", "/products", json=self._to_shoper_payload(product)
        )
        body = response.json()
        product_id = body.get("product_id") or body.get("id")
        return await self.get_product(str(product_id))

    async def update_product(
        self, external_id: str, product: ConnectorProduct
    ) -> ConnectorProduct:
        await self._request(
            "PUT", f"/products/{external_id}", json=self._to_shoper_payload(product)
        )
        return await self.get_product(external_id)

    async def update_price(self, update: PriceUpdate) -> None:
        current = await self._request("GET", f"/products/{update.external_id}")
        stock = dict(current.json().get("stock") or {})
        stock["price"] = str(update.price)
        await self._request(
            "PUT", f"/products/{update.external_id}", json={"stock": stock}
        )

    async def update_stock(self, update: StockUpdate) -> None:
        current = await self._request("GET", f"/products/{update.external_id}")
        stock = dict(current.json().get("stock") or {})
        stock["stock"] = update.quantity
        await self._request(
            "PUT", f"/products/{update.external_id}", json={"stock": stock}
        )

    async def get_categories(self) -> list[ConnectorCategory]:
        response = await self._request("GET", "/categories", params={"limit": 100})
        categories = []
        for raw in response.json().get("list", []):
            translation = self._translation(raw)
            categories.append(
                ConnectorCategory(
                    external_id=str(raw["category_id"]),
                    name=translation.get("name") or raw.get("name") or "",
                    parent_external_id=(
                        str(raw["parent_id"]) if raw.get("parent_id") else None
                    ),
                )
            )
        return categories

    async def upload_image(self, external_id: str, image_url: str) -> UploadedImage:
        """Best-effort: the exact product-images request shape wasn't
        confirmed (see class docstring) - verify against a real store."""
        await self._request(
            "POST",
            "/product-images",
            json={"product_id": int(external_id), "url": image_url},
        )
        return UploadedImage(external_id=external_id, url=image_url)

    async def get_category_parameters(self, category_external_id: str) -> list[CategoryParameter]:
        """No per-category mandatory-parameter concept found - always
        empty, same as WooCommerceConnector."""
        return []

    async def publish_offer(self, external_id: str) -> None:
        current = await self._request("GET", f"/products/{external_id}")
        translation = dict(self._translation(current.json()))
        translation["active"] = 1
        await self._request(
            "PUT",
            f"/products/{external_id}",
            json={"translations": {self._locale: translation}},
        )
