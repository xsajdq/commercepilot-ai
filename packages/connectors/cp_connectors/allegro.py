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
ALLEGRO_API_BASE_URL = "https://api.allegro.pl"
_ACCEPT_HEADER = "application/vnd.allegro.public.v1+json"


class AllegroConnector:
    """CommerceConnector for an Allegro seller account, via Allegro's
    REST API. Auth is a Bearer access token obtained through OAuth2
    Authorization Code (see allegro_oauth.py) - this class does not
    itself perform the OAuth dance, only uses an already-issued token. A
    call that fails with ConnectorAuthError most likely means the token
    expired; the caller should refresh it
    (allegro_oauth.refresh_access_token) and retry with a fresh
    AllegroConnector, not treat it as a permanent failure.

    Allegro's offer model is meaningfully different from a simple
    product, and this connector deliberately does not hide that:

    - An offer belongs to exactly one category, and that category has its
      own mandatory parameters (get_category_parameters) - set them via
      ConnectorProduct.parameters ({parameter_id: [value_id_or_text]}).
    - Images must be uploaded to Allegro's own image host before being
      referenced (upload_image does both steps).
    - create_product/update_product always leave the offer as a draft
      (publication.status=INACTIVE); publish_offer is the only path to
      making it live, matching Allegro's real create-then-publish flow.
    - get_categories only returns Allegro's top-level categories - the
      real category tree is deep, and CommerceConnector's generic
      signature has no way to request a specific parent's children.
    - Delivery/shipping template assignment isn't modeled - a real
      production create_product call needs one and this doesn't send it.
    - Offer descriptions are a structured "sections" rich-text format,
      not plain text, so ConnectorProduct.description round-trips as
      None for now.

    Retry/backoff/rate-limit handling is deliberately NOT done here -
    that's the sync engine's job (Phase 6).
    """

    def __init__(
        self,
        *,
        access_token: str,
        api_base_url: str = ALLEGRO_API_BASE_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(
            base_url=api_base_url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": _ACCEPT_HEADER,
                "Content-Type": _ACCEPT_HEADER,
            },
            timeout=_DEFAULT_TIMEOUT_SECONDS,
        )

    async def __aenter__(self) -> "AllegroConnector":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        response = await self._client.request(method, path, **kwargs)
        if response.status_code in (401, 403):
            raise ConnectorAuthError(f"Allegro rejected the access token: {response.text}")
        if response.status_code == 404:
            raise ConnectorNotFoundError(f"Allegro 404 for {method} {path}")
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            raise ConnectorRateLimitError(
                "Allegro rate limit hit",
                retry_after_seconds=float(retry_after) if retry_after else None,
            )
        if response.status_code >= 400:
            raise ConnectorError(
                f"Allegro {method} {path} failed with {response.status_code}: {response.text}"
            )
        return response

    @staticmethod
    def _to_connector_product(raw: dict[str, Any]) -> ConnectorProduct:
        selling_mode = raw.get("sellingMode") or {}
        price_raw = (selling_mode.get("price") or {}).get("amount")
        try:
            price = Decimal(str(price_raw)) if price_raw not in (None, "") else None
        except InvalidOperation:
            price = None

        category = raw.get("category") or {}
        parameters = {
            p["id"]: p.get("valuesIds") or p.get("values") or []
            for p in raw.get("parameters") or []
        }

        return ConnectorProduct(
            external_id=raw.get("id"),
            sku=(raw.get("external") or {}).get("id") or "",
            name=raw.get("name") or "",
            price=price,
            stock_quantity=(raw.get("stock") or {}).get("available"),
            category_external_id=category.get("id"),
            image_urls=[img["url"] for img in raw.get("images") or [] if img.get("url")],
            status=((raw.get("publication") or {}).get("status") or "INACTIVE").lower(),
            parameters=parameters,
        )

    @staticmethod
    def _to_allegro_payload(product: ConnectorProduct) -> dict[str, Any]:
        """Always writes publication.status=INACTIVE - publish_offer is
        the only way to make an offer live (see class docstring)."""
        payload: dict[str, Any] = {
            "name": product.name,
            "publication": {"status": "INACTIVE"},
        }
        if product.sku:
            payload["external"] = {"id": product.sku}
        if product.category_external_id is not None:
            payload["category"] = {"id": product.category_external_id}
        if product.price is not None:
            payload["sellingMode"] = {
                "price": {"amount": str(product.price), "currency": product.currency}
            }
        if product.stock_quantity is not None:
            payload["stock"] = {"available": product.stock_quantity, "unit": "UNIT"}
        if product.image_urls:
            payload["images"] = [{"url": url} for url in product.image_urls]
        if product.parameters:
            payload["parameters"] = [
                {"id": param_id, "valuesIds": values}
                for param_id, values in product.parameters.items()
            ]
        return payload

    async def get_products(
        self, *, cursor: str | None = None, limit: int = 50
    ) -> tuple[list[ConnectorProduct], str | None]:
        offset = int(cursor) if cursor else 0
        response = await self._request(
            "GET", "/sale/offers", params={"offset": offset, "limit": limit}
        )
        body = response.json()
        offers = [self._to_connector_product(raw) for raw in body.get("offers", [])]
        total_count = body.get("totalCount", offset + len(offers))
        next_cursor = str(offset + limit) if offset + limit < total_count else None
        return offers, next_cursor

    async def get_product(self, external_id: str) -> ConnectorProduct:
        response = await self._request("GET", f"/sale/offers/{external_id}")
        return self._to_connector_product(response.json())

    async def create_product(self, product: ConnectorProduct) -> ConnectorProduct:
        response = await self._request(
            "POST", "/sale/offers", json=self._to_allegro_payload(product)
        )
        return self._to_connector_product(response.json())

    async def update_product(
        self, external_id: str, product: ConnectorProduct
    ) -> ConnectorProduct:
        response = await self._request(
            "PUT", f"/sale/offers/{external_id}", json=self._to_allegro_payload(product)
        )
        return self._to_connector_product(response.json())

    async def update_price(self, update: PriceUpdate) -> None:
        await self._request(
            "PUT",
            f"/sale/offers/{update.external_id}",
            json={
                "sellingMode": {
                    "price": {"amount": str(update.price), "currency": update.currency}
                }
            },
        )

    async def update_stock(self, update: StockUpdate) -> None:
        await self._request(
            "PUT",
            f"/sale/offers/{update.external_id}",
            json={"stock": {"available": update.quantity, "unit": "UNIT"}},
        )

    async def get_categories(self) -> list[ConnectorCategory]:
        """Only top-level categories - see class docstring."""
        response = await self._request("GET", "/sale/categories")
        return [
            ConnectorCategory(
                external_id=raw["id"],
                name=raw["name"],
                parent_external_id=(raw.get("parent") or {}).get("id"),
            )
            for raw in response.json().get("categories", [])
        ]

    async def get_category_parameters(self, category_external_id: str) -> list[CategoryParameter]:
        response = await self._request(
            "GET", f"/sale/categories/{category_external_id}/parameters"
        )
        parameters = []
        for raw in response.json().get("parameters", []):
            dictionary = raw.get("dictionary") or []
            parameters.append(
                CategoryParameter(
                    external_id=raw["id"],
                    name=raw["name"],
                    required=bool(raw.get("required")),
                    dictionary_values=[{"id": d["id"], "value": d["value"]} for d in dictionary],
                )
            )
        return parameters

    async def upload_image(self, external_id: str, image_url: str) -> UploadedImage:
        """Allegro requires images to be hosted by Allegro itself - this
        first asks Allegro to fetch image_url into its own image host,
        then appends the returned Allegro-hosted URL to the offer."""
        hosted = await self._request("POST", "/sale/images", json={"url": image_url})
        hosted_url = hosted.json()["location"]

        current = await self.get_product(external_id)
        await self._request(
            "PUT",
            f"/sale/offers/{external_id}",
            json={"images": [{"url": url} for url in [*current.image_urls, hosted_url]]},
        )
        return UploadedImage(external_id=external_id, url=hosted_url)

    async def publish_offer(self, external_id: str) -> None:
        await self._request(
            "PUT", f"/sale/offers/{external_id}", json={"publication": {"status": "ACTIVE"}}
        )
