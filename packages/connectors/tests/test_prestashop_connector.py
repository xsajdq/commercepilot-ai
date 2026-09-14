import base64
from decimal import Decimal
from xml.etree import ElementTree as ET

import httpx
import pytest
import pytest_asyncio

from cp_connectors.exceptions import (
    ConnectorAuthError,
    ConnectorError,
    ConnectorNotFoundError,
    ConnectorRateLimitError,
)
from cp_connectors.prestashop import PrestaShopConnector
from cp_connectors.types import ConnectorProduct, PriceUpdate, StockUpdate

_IMAGE_URL = "https://images.example.com/photo.jpg"


class FakePrestaShopAPI:
    """A minimal in-memory stand-in for a PrestaShop store's Webservice
    API, driven through httpx.MockTransport - no real store, no network.
    Reads respond in JSON (matching output_format=JSON); writes are
    parsed as XML (matching what PrestaShopConnector actually sends)."""

    def __init__(self, *, api_key: str = "key_test") -> None:
        self.api_key = api_key
        self.products: dict[int, dict] = {}
        self.stock_availables: dict[int, dict] = {}
        self.categories: list[dict] = [
            {"id": 2, "id_parent": 0, "name": [{"id": "1", "value": "Home"}]},
        ]
        self._next_product_id = 1
        self._next_stock_id = 1
        self.rate_limited_once = False
        self.error_once_with_status: int | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        if str(request.url) == _IMAGE_URL:
            return httpx.Response(200, content=b"fake-image-bytes")

        auth_header = request.headers.get("Authorization", "")
        expected = "Basic " + base64.b64encode(f"{self.api_key}:".encode()).decode()
        if auth_header != expected:
            return httpx.Response(401, json={"error": "invalid credentials"})

        if self.rate_limited_once:
            self.rate_limited_once = False
            return httpx.Response(429, headers={"Retry-After": "4"}, json={"error": "slow down"})
        if self.error_once_with_status is not None:
            status = self.error_once_with_status
            self.error_once_with_status = None
            return httpx.Response(status, json={"error": "server exploded"})

        path = request.url.path
        method = request.method
        query = dict(httpx.QueryParams(request.url.query))

        if path == "/api/products" and method == "GET":
            return self._list_products(query)
        if path == "/api/products" and method == "POST":
            return self._create_product(request)
        if path.startswith("/api/products/") and path.count("/") == 3:
            return self._product_detail(path, method, request)
        if path == "/api/stock_availables" and method == "GET":
            return self._list_stock(query)
        if path.startswith("/api/stock_availables/") and method == "PATCH":
            return self._patch_stock(path, request)
        if path == "/api/categories" and method == "GET":
            return httpx.Response(200, json={"categories": self.categories})
        if path.startswith("/api/images/products/") and method == "POST":
            return httpx.Response(200, json={"image": {"id": 999}})

        return httpx.Response(404, json={"error": "unhandled route"})

    def _list_products(self, query: dict[str, str]) -> httpx.Response:
        limit = query.get("limit", "0,50")
        offset_str, count_str = limit.split(",")
        offset, count = int(offset_str), int(count_str)
        ids = sorted(self.products)
        page_ids = ids[offset : offset + count]
        return httpx.Response(200, json={"products": [self.products[i] for i in page_ids]})

    def _create_product(self, request: httpx.Request) -> httpx.Response:
        fields = _parse_xml_fields(request.content, "product")
        product_id = self._next_product_id
        self._next_product_id += 1
        record = _apply_fields({"id": product_id, "active": "0"}, fields)
        self.products[product_id] = record

        stock_id = self._next_stock_id
        self._next_stock_id += 1
        self.stock_availables[stock_id] = {"id": stock_id, "id_product": product_id, "quantity": 0}

        return httpx.Response(201, json={"product": record})

    def _product_detail(self, path: str, method: str, request: httpx.Request) -> httpx.Response:
        product_id_str = path.rsplit("/", 1)[-1]
        if not product_id_str.isdigit() or int(product_id_str) not in self.products:
            return httpx.Response(404, json={"error": "not found"})
        product_id = int(product_id_str)

        if method == "GET":
            return httpx.Response(200, json={"product": self.products[product_id]})

        fields = _parse_xml_fields(request.content, "product")
        if method == "PUT":
            self.products[product_id] = _apply_fields({"id": product_id}, fields)
        else:  # PATCH
            self.products[product_id] = _apply_fields(self.products[product_id], fields)
        return httpx.Response(200, json={"product": self.products[product_id]})

    def _list_stock(self, query: dict[str, str]) -> httpx.Response:
        raw_filter = query.get("filter[id_product]", "")
        wanted = {int(x) for x in raw_filter.strip("[]").split("|") if x}
        matches = [r for r in self.stock_availables.values() if r["id_product"] in wanted]
        return httpx.Response(200, json={"stock_availables": matches})

    def _patch_stock(self, path: str, request: httpx.Request) -> httpx.Response:
        stock_id_str = path.rsplit("/", 1)[-1]
        if not stock_id_str.isdigit() or int(stock_id_str) not in self.stock_availables:
            return httpx.Response(404, json={"error": "not found"})
        stock_id = int(stock_id_str)
        fields = _parse_xml_fields(request.content, "stock_available")
        record = self.stock_availables[stock_id]
        if "quantity" in fields:
            record["quantity"] = int(fields["quantity"])
        return httpx.Response(200, json={"stock_available": record})


def _parse_xml_fields(content: bytes, resource: str) -> dict[str, str]:
    root = ET.fromstring(content)
    node = root.find(resource)
    fields: dict[str, str] = {}
    for child in node:
        lang = child.find("language")
        if lang is not None:
            fields[child.tag] = lang.text or ""
        else:
            fields[child.tag] = child.text or ""
    return fields


def _apply_fields(base: dict, fields: dict[str, str]) -> dict:
    record = dict(base)
    for key, value in fields.items():
        if key in ("name", "description"):
            record[key] = [{"id": "1", "value": value}]
        elif key == "id":
            continue
        else:
            record[key] = value
    return record


@pytest.fixture
def fake_api() -> FakePrestaShopAPI:
    return FakePrestaShopAPI()


@pytest_asyncio.fixture
async def connector(fake_api: FakePrestaShopAPI):
    client = httpx.AsyncClient(
        base_url="https://shop.example.com/api",
        auth=(fake_api.api_key, ""),
        transport=httpx.MockTransport(fake_api.handler),
    )
    conn = PrestaShopConnector(
        store_url="https://shop.example.com", api_key=fake_api.api_key, client=client
    )
    yield conn
    await conn.aclose()


@pytest_asyncio.fixture
async def bad_connector(fake_api: FakePrestaShopAPI):
    client = httpx.AsyncClient(
        base_url="https://shop.example.com/api",
        auth=("wrong", ""),
        transport=httpx.MockTransport(fake_api.handler),
    )
    conn = PrestaShopConnector(store_url="https://shop.example.com", api_key="wrong", client=client)
    yield conn
    await conn.aclose()


async def test_invalid_credentials_raise_connector_auth_error(bad_connector) -> None:
    with pytest.raises(ConnectorAuthError):
        await bad_connector.get_products()


async def test_create_then_get_product(connector: PrestaShopConnector) -> None:
    created = await connector.create_product(
        ConnectorProduct(sku="SKU-1", name="Chaise", price=Decimal("149.00"), stock_quantity=10)
    )
    assert created.external_id is not None
    assert created.sku == "SKU-1"
    assert created.name == "Chaise"
    assert created.price == Decimal("149.00")
    assert created.stock_quantity == 10

    fetched = await connector.get_product(created.external_id)
    assert fetched.sku == "SKU-1"
    assert fetched.price == Decimal("149.00")
    assert fetched.stock_quantity == 10


async def test_get_unknown_product_raises_not_found(connector: PrestaShopConnector) -> None:
    with pytest.raises(ConnectorNotFoundError):
        await connector.get_product("999")


async def test_update_price_does_not_wipe_stock(connector: PrestaShopConnector) -> None:
    created = await connector.create_product(
        ConnectorProduct(sku="SKU-2", name="Table", price=Decimal("10.00"), stock_quantity=5)
    )

    await connector.update_price(
        PriceUpdate(external_id=created.external_id, price=Decimal("29.99"))
    )

    fetched = await connector.get_product(created.external_id)
    assert fetched.price == Decimal("29.99")
    assert fetched.stock_quantity == 5


async def test_update_stock_does_not_wipe_price(connector: PrestaShopConnector) -> None:
    created = await connector.create_product(
        ConnectorProduct(sku="SKU-3", name="Lampe", price=Decimal("40.00"), stock_quantity=2)
    )

    await connector.update_stock(StockUpdate(external_id=created.external_id, quantity=7))

    fetched = await connector.get_product(created.external_id)
    assert fetched.stock_quantity == 7
    assert fetched.price == Decimal("40.00")


async def test_update_stock_for_unknown_product_raises(connector: PrestaShopConnector) -> None:
    with pytest.raises(ConnectorNotFoundError):
        await connector.update_stock(StockUpdate(external_id="999", quantity=1))


async def test_pagination_walks_every_product_exactly_once(connector: PrestaShopConnector) -> None:
    for i in range(5):
        await connector.create_product(ConnectorProduct(sku=f"SKU-{i}", name=f"Produit {i}"))

    seen: list[str] = []
    cursor: str | None = None
    for _ in range(10):
        page, cursor = await connector.get_products(cursor=cursor, limit=2)
        seen.extend(p.external_id for p in page)
        if cursor is None:
            break

    assert len(seen) == 5
    assert len(set(seen)) == 5


async def test_get_categories_maps_localized_name_and_parent(
    connector: PrestaShopConnector,
) -> None:
    categories = await connector.get_categories()
    assert len(categories) == 1
    assert categories[0].external_id == "2"
    assert categories[0].name == "Home"
    assert categories[0].parent_external_id is None


async def test_rate_limit_raises_with_retry_after(
    connector: PrestaShopConnector, fake_api: FakePrestaShopAPI
) -> None:
    fake_api.rate_limited_once = True
    with pytest.raises(ConnectorRateLimitError) as exc_info:
        await connector.get_products()
    assert exc_info.value.retry_after_seconds == 4.0


async def test_server_error_raises_generic_connector_error(
    connector: PrestaShopConnector, fake_api: FakePrestaShopAPI
) -> None:
    fake_api.error_once_with_status = 500
    with pytest.raises(ConnectorError):
        await connector.get_products()


async def test_get_category_parameters_is_always_empty(connector: PrestaShopConnector) -> None:
    assert await connector.get_category_parameters("2") == []


async def test_publish_offer_sets_active_and_preserves_price(
    connector: PrestaShopConnector,
) -> None:
    created = await connector.create_product(
        ConnectorProduct(sku="SKU-4", name="Miroir", price=Decimal("55.00"), status="draft")
    )
    assert created.status == "draft"

    await connector.publish_offer(created.external_id)

    fetched = await connector.get_product(created.external_id)
    assert fetched.status == "active"
    assert fetched.price == Decimal("55.00")


async def test_publish_offer_for_unknown_product_raises(connector: PrestaShopConnector) -> None:
    with pytest.raises(ConnectorNotFoundError):
        await connector.publish_offer("999")


async def test_upload_image_downloads_then_uploads_bytes(connector: PrestaShopConnector) -> None:
    created = await connector.create_product(ConnectorProduct(sku="SKU-5", name="Vase"))
    uploaded = await connector.upload_image(created.external_id, _IMAGE_URL)
    assert uploaded.url == _IMAGE_URL
