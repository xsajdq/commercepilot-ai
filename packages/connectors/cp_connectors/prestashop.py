from decimal import Decimal, InvalidOperation
from typing import Any
from xml.etree import ElementTree as ET

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
_DEFAULT_LANGUAGE_ID = "1"


class PrestaShopConnector:
    """CommerceConnector for a PrestaShop store, via PrestaShop's
    Webservice API (`{store_url}/api`) - confirmed against PrestaShop's
    official developer docs, GitHub issues, and its own published
    Postman collection (`PrestaShop/webservice-postman-examples`), not
    just inferred:

    Confirmed:
    - Auth: HTTP Basic with the webservice key as username, empty
      password (generated in Admin -> Advanced Parameters -> Webservice).
    - Reads: append `output_format=JSON` for JSON instead of PrestaShop's
      default XML. A plain list request (`GET /api/products`) returns
      bare ids only - `display=full` is required to get full objects.
    - Writes (POST/PUT/PATCH) must send an XML body regardless of the
      read format - PrestaShop 8.1+ can output JSON but cannot parse
      JSON *input*, and sending XML always works across older versions
      too, so this class always writes XML.
    - Stock quantity is NOT a product field - it lives in a separate
      `stock_availables` resource keyed by `id_product` (one is
      auto-created when a product is created). Reading/writing stock
      means finding that record first, not touching the product itself.
    - Multi-language fields (`name`, `description`) are lists of
      `{"id": <language_id>, "value": ...}` in JSON, or
      `<language id="...">` elements in XML - not a single string.
    - Image upload is `POST /api/images/products/{id}` as
      `multipart/form-data` with the raw image bytes under an `image`
      field - not a URL reference like WooCommerce/Shoper.
    - `PATCH` is supported for partial updates.

    Simplifications (documented, not hidden - same spirit as
    WooCommerce's "first category only" note):
    - Only language id "1" is read/written; a multi-language store's
      other languages are never touched.
    - `get_categories`' `parent_external_id` is just "does `id_parent`
      have a truthy value", without modeling PrestaShop's own Root/Home
      super-category convention.
    - No official total-item-count header was confirmed for list
      pagination, so `get_products` uses the standard "a short page
      means it was the last one" rule instead of trusting an unverified
      header.
    - `get_category_parameters` always returns `[]` - no per-category
      mandatory-attribute concept exists in PrestaShop's default
      catalog, same as WooCommerce/Shoper.

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
            base_url=store_url.rstrip("/") + "/api",
            auth=(api_key, ""),
            timeout=_DEFAULT_TIMEOUT_SECONDS,
        )

    async def __aenter__(self) -> "PrestaShopConnector":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        params = {"output_format": "JSON", **kwargs.pop("params", {})}
        response = await self._client.request(method, path, params=params, **kwargs)
        if response.status_code in (401, 403):
            raise ConnectorAuthError(f"PrestaShop rejected credentials: {response.text}")
        if response.status_code == 404:
            raise ConnectorNotFoundError(f"PrestaShop 404 for {method} {path}")
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            raise ConnectorRateLimitError(
                "PrestaShop rate limit hit",
                retry_after_seconds=float(retry_after) if retry_after else None,
            )
        if response.status_code >= 400:
            raise ConnectorError(
                f"PrestaShop {method} {path} failed with {response.status_code}: {response.text}"
            )
        return response

    @staticmethod
    def _localized(value: Any) -> str | None:
        """Multi-language fields come back as a list of
        {"id": ..., "value": ...} - pull out _DEFAULT_LANGUAGE_ID (or the
        first entry if that id isn't present); a plain string is
        returned as-is for shops that flatten single-language fields."""
        if isinstance(value, str):
            return value or None
        if isinstance(value, list):
            for entry in value:
                if str(entry.get("id")) == _DEFAULT_LANGUAGE_ID:
                    return entry.get("value") or None
            if value:
                return value[0].get("value") or None
        return None

    def _to_connector_product(
        self, raw: dict[str, Any], *, stock_quantity: int | None
    ) -> ConnectorProduct:
        price_raw = raw.get("price")
        try:
            price = Decimal(str(price_raw)) if price_raw not in (None, "") else None
        except InvalidOperation:
            price = None

        category_id = raw.get("id_category_default")
        return ConnectorProduct(
            external_id=str(raw["id"]),
            sku=raw.get("reference") or "",
            name=self._localized(raw.get("name")) or "",
            description=self._localized(raw.get("description")),
            price=price,
            stock_quantity=stock_quantity,
            category_external_id=str(category_id) if category_id not in (None, "0", 0) else None,
            status="active" if str(raw.get("active")) == "1" else "draft",
        )

    def _build_xml(self, resource: str, fields: dict[str, Any]) -> bytes:
        root = ET.Element("prestashop")
        node = ET.SubElement(root, resource)
        for key, value in fields.items():
            if key in ("name", "description"):
                container = ET.SubElement(node, key)
                lang = ET.SubElement(container, "language")
                lang.set("id", _DEFAULT_LANGUAGE_ID)
                lang.text = str(value)
            else:
                child = ET.SubElement(node, key)
                child.text = str(value)
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)

    def _product_fields(self, product: ConnectorProduct) -> dict[str, Any]:
        fields: dict[str, Any] = {
            "reference": product.sku,
            "name": product.name,
            "active": 1 if product.status == "active" else 0,
        }
        if product.description is not None:
            fields["description"] = product.description
        if product.price is not None:
            fields["price"] = str(product.price)
        if product.category_external_id is not None:
            fields["id_category_default"] = product.category_external_id
        return fields

    async def _stock_available_id(self, product_external_id: str) -> str | None:
        response = await self._request(
            "GET",
            "/stock_availables",
            params={"display": "full", "filter[id_product]": product_external_id},
        )
        records = response.json().get("stock_availables") or []
        return str(records[0]["id"]) if records else None

    async def _stock_quantities(self, product_external_ids: list[str]) -> dict[str, int]:
        if not product_external_ids:
            return {}
        response = await self._request(
            "GET",
            "/stock_availables",
            params={
                "display": "full",
                "filter[id_product]": "[" + "|".join(product_external_ids) + "]",
            },
        )
        records = response.json().get("stock_availables") or []
        quantities: dict[str, int] = {}
        for record in records:
            id_product = str(record.get("id_product"))
            if "quantity" in record:
                quantities[id_product] = int(record["quantity"])
        return quantities

    async def _set_stock(self, product_external_id: str, quantity: int) -> None:
        stock_id = await self._stock_available_id(product_external_id)
        if stock_id is None:
            return
        xml = self._build_xml("stock_available", {"id": stock_id, "quantity": quantity})
        await self._request(
            "PATCH", f"/stock_availables/{stock_id}", content=xml,
            headers={"Content-Type": "text/xml"},
        )

    async def get_products(
        self, *, cursor: str | None = None, limit: int = 50
    ) -> tuple[list[ConnectorProduct], str | None]:
        offset = int(cursor) if cursor else 0
        response = await self._request(
            "GET",
            "/products",
            params={"display": "full", "limit": f"{offset},{limit}"},
        )
        raw_products = response.json().get("products") or []
        if isinstance(raw_products, dict):
            raw_products = [raw_products]

        quantities = await self._stock_quantities([str(p["id"]) for p in raw_products])
        products = [
            self._to_connector_product(raw, stock_quantity=quantities.get(str(raw["id"])))
            for raw in raw_products
        ]
        next_cursor = str(offset + limit) if len(raw_products) == limit else None
        return products, next_cursor

    async def get_product(self, external_id: str) -> ConnectorProduct:
        response = await self._request(
            "GET", f"/products/{external_id}", params={"display": "full"}
        )
        raw = response.json()["product"]
        quantities = await self._stock_quantities([external_id])
        return self._to_connector_product(raw, stock_quantity=quantities.get(external_id))

    async def create_product(self, product: ConnectorProduct) -> ConnectorProduct:
        xml = self._build_xml("product", self._product_fields(product))
        response = await self._request(
            "POST", "/products", content=xml, headers={"Content-Type": "text/xml"}
        )
        new_id = str(response.json()["product"]["id"])
        if product.stock_quantity is not None:
            await self._set_stock(new_id, product.stock_quantity)
        return await self.get_product(new_id)

    async def update_product(
        self, external_id: str, product: ConnectorProduct
    ) -> ConnectorProduct:
        fields = {"id": external_id, **self._product_fields(product)}
        xml = self._build_xml("product", fields)
        await self._request(
            "PUT", f"/products/{external_id}", content=xml, headers={"Content-Type": "text/xml"}
        )
        if product.stock_quantity is not None:
            await self._set_stock(external_id, product.stock_quantity)
        return await self.get_product(external_id)

    async def update_price(self, update: PriceUpdate) -> None:
        xml = self._build_xml(
            "product", {"id": update.external_id, "price": str(update.price)}
        )
        await self._request(
            "PATCH",
            f"/products/{update.external_id}",
            content=xml,
            headers={"Content-Type": "text/xml"},
        )

    async def update_stock(self, update: StockUpdate) -> None:
        # Confirms the product exists (raises ConnectorNotFoundError
        # otherwise) before touching its separate stock_availables record.
        await self._request("GET", f"/products/{update.external_id}")
        await self._set_stock(update.external_id, update.quantity)

    async def get_categories(self) -> list[ConnectorCategory]:
        response = await self._request(
            "GET", "/categories", params={"display": "full", "limit": "0,100"}
        )
        categories = []
        for raw in response.json().get("categories") or []:
            parent_id = raw.get("id_parent")
            categories.append(
                ConnectorCategory(
                    external_id=str(raw["id"]),
                    name=self._localized(raw.get("name")) or "",
                    parent_external_id=(
                        str(parent_id) if parent_id not in (None, "0", 0) else None
                    ),
                )
            )
        return categories

    async def upload_image(self, external_id: str, image_url: str) -> UploadedImage:
        """PrestaShop requires the actual image bytes, not a URL
        reference - fetches image_url first, then uploads the bytes."""
        source = await self._client.get(image_url)
        if source.status_code >= 400:
            raise ConnectorError(f"Could not download image from {image_url}")

        response = await self._request(
            "POST",
            f"/images/products/{external_id}",
            files={"image": ("image", source.content)},
        )
        image_id = response.json().get("image", {}).get("id")
        return UploadedImage(external_id=str(image_id) if image_id else external_id, url=image_url)

    async def get_category_parameters(self, category_external_id: str) -> list[CategoryParameter]:
        """No per-category mandatory-parameter concept exists in
        PrestaShop's default catalog - always empty, same as
        WooCommerceConnector/ShoperConnector."""
        return []

    async def publish_offer(self, external_id: str) -> None:
        """PrestaShop products go live as soon as `active=1`; this just
        ensures that via a partial PATCH (raises ConnectorNotFoundError
        via _request if external_id doesn't exist)."""
        xml = self._build_xml("product", {"id": external_id, "active": 1})
        await self._request(
            "PATCH",
            f"/products/{external_id}",
            content=xml,
            headers={"Content-Type": "text/xml"},
        )
