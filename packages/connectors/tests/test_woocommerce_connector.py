import json
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio

from cp_connectors.exceptions import (
    ConnectorAuthError,
    ConnectorError,
    ConnectorNotFoundError,
    ConnectorRateLimitError,
)
from cp_connectors.types import ConnectorProduct, PriceUpdate, StockUpdate
from cp_connectors.woocommerce import WooCommerceConnector


class FakeWooCommerceAPI:
    """A minimal in-memory stand-in for a WooCommerce store's REST API,
    driven through httpx.MockTransport - no real store, no network."""

    def __init__(self) -> None:
        self.products: dict[int, dict] = {}
        self.categories: list[dict] = [{"id": 9, "name": "Shoes", "parent": 0}]
        self._next_id = 1
        self.rate_limited_once = False
        self.error_once_with_status: int | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        query = dict(httpx.QueryParams(request.url.query))
        if query.get("consumer_key") != "ck_test" or query.get("consumer_secret") != "cs_test":
            return httpx.Response(401, json={"message": "invalid credentials"})

        if self.rate_limited_once:
            self.rate_limited_once = False
            return httpx.Response(
                429, headers={"Retry-After": "2"}, json={"message": "too many requests"}
            )
        if self.error_once_with_status is not None:
            status = self.error_once_with_status
            self.error_once_with_status = None
            return httpx.Response(status, json={"message": "server exploded"})

        path = request.url.path
        method = request.method

        if path == "/wp-json/wc/v3/products/categories" and method == "GET":
            return httpx.Response(200, json=self.categories)

        if path == "/wp-json/wc/v3/products" and method == "GET":
            return self._list_products(query)

        if path == "/wp-json/wc/v3/products" and method == "POST":
            return self._create_product(request)

        if path.startswith("/wp-json/wc/v3/products/") and method in ("GET", "PUT"):
            return self._product_detail(path, method, request)

        return httpx.Response(404, json={"message": "unhandled route"})

    def _list_products(self, query: dict[str, str]) -> httpx.Response:
        page = int(query.get("page", 1))
        per_page = int(query.get("per_page", 50))
        ids = sorted(self.products)
        start = (page - 1) * per_page
        page_ids = ids[start : start + per_page]
        total_pages = max(1, -(-len(ids) // per_page))
        return httpx.Response(
            200,
            json=[self.products[i] for i in page_ids],
            headers={"X-WP-TotalPages": str(total_pages)},
        )

    def _create_product(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        product_id = self._next_id
        self._next_id += 1
        record = {"id": product_id, "images": [], "categories": [], **body}
        self.products[product_id] = record
        return httpx.Response(201, json=record)

    def _product_detail(self, path: str, method: str, request: httpx.Request) -> httpx.Response:
        product_id_str = path.rsplit("/", 1)[-1]
        if not product_id_str.isdigit() or int(product_id_str) not in self.products:
            return httpx.Response(404, json={"message": "not found"})
        product_id = int(product_id_str)
        if method == "GET":
            return httpx.Response(200, json=self.products[product_id])
        body = json.loads(request.content)
        self.products[product_id].update(body)
        return httpx.Response(200, json=self.products[product_id])


@pytest.fixture
def fake_api() -> FakeWooCommerceAPI:
    return FakeWooCommerceAPI()


@pytest_asyncio.fixture
async def connector(fake_api: FakeWooCommerceAPI):
    client = httpx.AsyncClient(
        base_url="https://shop.example.com/wp-json/wc/v3",
        params={"consumer_key": "ck_test", "consumer_secret": "cs_test"},
        transport=httpx.MockTransport(fake_api.handler),
    )
    conn = WooCommerceConnector(
        store_url="https://shop.example.com",
        consumer_key="ck_test",
        consumer_secret="cs_test",
        client=client,
    )
    yield conn
    await conn.aclose()


@pytest_asyncio.fixture
async def bad_connector(fake_api: FakeWooCommerceAPI):
    client = httpx.AsyncClient(
        base_url="https://shop.example.com/wp-json/wc/v3",
        params={"consumer_key": "wrong", "consumer_secret": "wrong"},
        transport=httpx.MockTransport(fake_api.handler),
    )
    conn = WooCommerceConnector(
        store_url="https://shop.example.com",
        consumer_key="wrong",
        consumer_secret="wrong",
        client=client,
    )
    yield conn
    await conn.aclose()


async def test_invalid_credentials_raise_connector_auth_error(bad_connector) -> None:
    with pytest.raises(ConnectorAuthError):
        await bad_connector.get_products()


async def test_create_then_get_product(connector: WooCommerceConnector) -> None:
    created = await connector.create_product(
        ConnectorProduct(sku="SKU-1", name="Running Shoe", price=Decimal("149.00"))
    )
    assert created.external_id is not None

    fetched = await connector.get_product(created.external_id)
    assert fetched.sku == "SKU-1"
    assert fetched.price == Decimal("149.00")


async def test_get_unknown_product_raises_not_found(connector: WooCommerceConnector) -> None:
    with pytest.raises(ConnectorNotFoundError):
        await connector.get_product("999")


async def test_update_price(connector: WooCommerceConnector) -> None:
    created = await connector.create_product(ConnectorProduct(sku="SKU-2", name="Hat"))
    await connector.update_price(
        PriceUpdate(external_id=created.external_id, price=Decimal("29.99"))
    )

    fetched = await connector.get_product(created.external_id)
    assert fetched.price == Decimal("29.99")


async def test_update_stock(connector: WooCommerceConnector) -> None:
    created = await connector.create_product(ConnectorProduct(sku="SKU-3", name="Bag"))
    await connector.update_stock(StockUpdate(external_id=created.external_id, quantity=7))

    fetched = await connector.get_product(created.external_id)
    assert fetched.stock_quantity == 7


async def test_update_price_for_unknown_product_raises(connector: WooCommerceConnector) -> None:
    with pytest.raises(ConnectorNotFoundError):
        await connector.update_price(PriceUpdate(external_id="999", price=Decimal("1.00")))


async def test_pagination_walks_every_product_exactly_once(
    connector: WooCommerceConnector,
) -> None:
    for i in range(5):
        await connector.create_product(ConnectorProduct(sku=f"SKU-{i}", name=f"Product {i}"))

    seen: list[str] = []
    cursor: str | None = None
    for _ in range(10):
        page, cursor = await connector.get_products(cursor=cursor, limit=2)
        seen.extend(p.external_id for p in page)
        if cursor is None:
            break

    assert len(seen) == 5
    assert len(set(seen)) == 5


async def test_get_categories_maps_parent(connector: WooCommerceConnector) -> None:
    categories = await connector.get_categories()
    assert len(categories) == 1
    assert categories[0].external_id == "9"
    assert categories[0].name == "Shoes"
    assert categories[0].parent_external_id is None


async def test_rate_limit_raises_with_retry_after(
    connector: WooCommerceConnector, fake_api: FakeWooCommerceAPI
) -> None:
    fake_api.rate_limited_once = True
    with pytest.raises(ConnectorRateLimitError) as exc_info:
        await connector.get_products()
    assert exc_info.value.retry_after_seconds == 2.0


async def test_server_error_raises_generic_connector_error(
    connector: WooCommerceConnector, fake_api: FakeWooCommerceAPI
) -> None:
    fake_api.error_once_with_status = 500
    with pytest.raises(ConnectorError):
        await connector.get_products()


async def test_upload_image_appends_to_existing_images(connector: WooCommerceConnector) -> None:
    created = await connector.create_product(
        ConnectorProduct(sku="SKU-4", name="Cap", image_urls=["https://example.com/a.jpg"])
    )

    uploaded = await connector.upload_image(created.external_id, "https://example.com/b.jpg")
    assert uploaded.url == "https://example.com/b.jpg"

    fetched = await connector.get_product(created.external_id)
    assert fetched.image_urls == ["https://example.com/a.jpg", "https://example.com/b.jpg"]
