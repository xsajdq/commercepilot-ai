import base64
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
from cp_connectors.shoper import ShoperConnector
from cp_connectors.types import ConnectorProduct, PriceUpdate, StockUpdate


class FakeShoperAPI:
    """A minimal in-memory stand-in for a Shoper store's REST API, driven
    through httpx.MockTransport - no real store, no network."""

    def __init__(self, *, client_id: str = "cid_test", client_secret: str = "secret_test") -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.valid_token = "tok_valid"
        self.products: dict[int, dict] = {}
        self.categories: list[dict] = [
            {
                "category_id": 3,
                "parent_id": 0,
                "translations": {"pl_PL": {"name": "Buty"}},
            }
        ]
        self._next_id = 1
        self.reject_bearer_once = False
        self.rate_limited_once = False
        self.error_once_with_status: int | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/webapi/rest/auth" and request.method == "POST":
            return self._handle_auth(request)

        auth_header = request.headers.get("Authorization", "")
        if self.reject_bearer_once:
            self.reject_bearer_once = False
            return httpx.Response(401, json={"error": "token invalid"})
        if auth_header != f"Bearer {self.valid_token}":
            return httpx.Response(401, json={"error": "missing or invalid token"})

        if self.rate_limited_once:
            self.rate_limited_once = False
            return httpx.Response(
                429, headers={"Retry-After": "3"}, json={"error": "too many requests"}
            )
        if self.error_once_with_status is not None:
            status = self.error_once_with_status
            self.error_once_with_status = None
            return httpx.Response(status, json={"error": "server exploded"})

        path = request.url.path
        method = request.method

        if path == "/webapi/rest/categories" and method == "GET":
            return httpx.Response(
                200, json={"count": 1, "pages": 1, "page": 1, "list": self.categories}
            )
        if path == "/webapi/rest/products" and method == "GET":
            return self._list_products(dict(httpx.QueryParams(request.url.query)))
        if path == "/webapi/rest/products" and method == "POST":
            return self._create_product(request)
        if path == "/webapi/rest/product-images" and method == "POST":
            return httpx.Response(201, json={"image_id": 1})
        if path.startswith("/webapi/rest/products/") and method in ("GET", "PUT"):
            return self._product_detail(path, method, request)

        return httpx.Response(404, json={"error": "unhandled route"})

    def _handle_auth(self, request: httpx.Request) -> httpx.Response:
        header = request.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return httpx.Response(401, json={"error": "missing credentials"})
        decoded = base64.b64decode(header.removeprefix("Basic ")).decode()
        client_id, _, client_secret = decoded.partition(":")
        if client_id != self.client_id or client_secret != self.client_secret:
            return httpx.Response(401, json={"error": "invalid credentials"})
        return httpx.Response(
            200,
            json={
                "access_token": self.valid_token,
                "token_type": "bearer",
                "expires_in": 2592000,
            },
        )

    def _list_products(self, query: dict[str, str]) -> httpx.Response:
        page = int(query.get("page", 1))
        limit = int(query.get("limit", 50))
        ids = sorted(self.products)
        start = (page - 1) * limit
        page_ids = ids[start : start + limit]
        pages = max(1, -(-len(ids) // limit))
        return httpx.Response(
            200,
            json={
                "count": len(ids),
                "pages": pages,
                "page": page,
                "list": [self.products[i] for i in page_ids],
            },
        )

    def _create_product(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        product_id = self._next_id
        self._next_id += 1
        record = {"product_id": product_id, **body}
        self.products[product_id] = record
        return httpx.Response(201, json={"product_id": product_id})

    def _product_detail(self, path: str, method: str, request: httpx.Request) -> httpx.Response:
        product_id_str = path.rsplit("/", 1)[-1]
        if not product_id_str.isdigit() or int(product_id_str) not in self.products:
            return httpx.Response(404, json={"error": "not found"})
        product_id = int(product_id_str)
        if method == "GET":
            return httpx.Response(200, json=self.products[product_id])
        body = json.loads(request.content)
        current = self.products[product_id]
        merged = {**current, **body}
        self.products[product_id] = merged
        return httpx.Response(200, json=merged)


@pytest.fixture
def fake_api() -> FakeShoperAPI:
    return FakeShoperAPI()


@pytest_asyncio.fixture
async def connector(fake_api: FakeShoperAPI):
    client = httpx.AsyncClient(
        base_url="https://shop.example.pl/webapi/rest",
        transport=httpx.MockTransport(fake_api.handler),
    )
    conn = ShoperConnector(
        store_url="https://shop.example.pl",
        client_id=fake_api.client_id,
        client_secret=fake_api.client_secret,
        client=client,
    )
    yield conn
    await conn.aclose()


@pytest_asyncio.fixture
async def bad_connector(fake_api: FakeShoperAPI):
    client = httpx.AsyncClient(
        base_url="https://shop.example.pl/webapi/rest",
        transport=httpx.MockTransport(fake_api.handler),
    )
    conn = ShoperConnector(
        store_url="https://shop.example.pl",
        client_id="wrong",
        client_secret="wrong",
        client=client,
    )
    yield conn
    await conn.aclose()


async def test_invalid_credentials_raise_connector_auth_error(bad_connector) -> None:
    with pytest.raises(ConnectorAuthError):
        await bad_connector.get_products()


async def test_create_then_get_product(connector: ShoperConnector) -> None:
    created = await connector.create_product(
        ConnectorProduct(sku="SKU-1", name="Buty biegowe", price=Decimal("149.00"))
    )
    assert created.external_id is not None
    assert created.sku == "SKU-1"
    assert created.name == "Buty biegowe"
    assert created.price == Decimal("149.00")

    fetched = await connector.get_product(created.external_id)
    assert fetched.sku == "SKU-1"
    assert fetched.price == Decimal("149.00")


async def test_get_unknown_product_raises_not_found(connector: ShoperConnector) -> None:
    with pytest.raises(ConnectorNotFoundError):
        await connector.get_product("999")


async def test_update_price_does_not_wipe_stock_quantity(connector: ShoperConnector) -> None:
    created = await connector.create_product(
        ConnectorProduct(sku="SKU-2", name="Czapka", price=Decimal("10.00"), stock_quantity=5)
    )

    await connector.update_price(
        PriceUpdate(external_id=created.external_id, price=Decimal("29.99"))
    )

    fetched = await connector.get_product(created.external_id)
    assert fetched.price == Decimal("29.99")
    assert fetched.stock_quantity == 5


async def test_update_stock_does_not_wipe_price(connector: ShoperConnector) -> None:
    created = await connector.create_product(
        ConnectorProduct(sku="SKU-3", name="Torba", price=Decimal("40.00"), stock_quantity=2)
    )

    await connector.update_stock(StockUpdate(external_id=created.external_id, quantity=7))

    fetched = await connector.get_product(created.external_id)
    assert fetched.stock_quantity == 7
    assert fetched.price == Decimal("40.00")


async def test_update_price_for_unknown_product_raises(connector: ShoperConnector) -> None:
    with pytest.raises(ConnectorNotFoundError):
        await connector.update_price(PriceUpdate(external_id="999", price=Decimal("1.00")))


async def test_pagination_walks_every_product_exactly_once(connector: ShoperConnector) -> None:
    for i in range(5):
        await connector.create_product(ConnectorProduct(sku=f"SKU-{i}", name=f"Produkt {i}"))

    seen: list[str] = []
    cursor: str | None = None
    for _ in range(10):
        page, cursor = await connector.get_products(cursor=cursor, limit=2)
        seen.extend(p.external_id for p in page)
        if cursor is None:
            break

    assert len(seen) == 5
    assert len(set(seen)) == 5


async def test_get_categories_maps_translation_name_and_parent(
    connector: ShoperConnector,
) -> None:
    categories = await connector.get_categories()
    assert len(categories) == 1
    assert categories[0].external_id == "3"
    assert categories[0].name == "Buty"
    assert categories[0].parent_external_id is None


async def test_rate_limit_raises_with_retry_after(
    connector: ShoperConnector, fake_api: FakeShoperAPI
) -> None:
    fake_api.rate_limited_once = True
    with pytest.raises(ConnectorRateLimitError) as exc_info:
        await connector.get_products()
    assert exc_info.value.retry_after_seconds == 3.0


async def test_server_error_raises_generic_connector_error(
    connector: ShoperConnector, fake_api: FakeShoperAPI
) -> None:
    fake_api.error_once_with_status = 500
    with pytest.raises(ConnectorError):
        await connector.get_products()


async def test_get_category_parameters_is_always_empty(connector: ShoperConnector) -> None:
    assert await connector.get_category_parameters("3") == []


async def test_publish_offer_sets_active_and_preserves_name(connector: ShoperConnector) -> None:
    created = await connector.create_product(
        ConnectorProduct(sku="SKU-4", name="Szalik", description="Ciepły szalik", status="draft")
    )
    assert created.status == "draft"

    await connector.publish_offer(created.external_id)

    fetched = await connector.get_product(created.external_id)
    assert fetched.status == "active"
    assert fetched.name == "Szalik"
    assert fetched.description == "Ciepły szalik"


async def test_publish_offer_for_unknown_product_raises(connector: ShoperConnector) -> None:
    with pytest.raises(ConnectorNotFoundError):
        await connector.publish_offer("999")


async def test_upload_image_returns_the_given_url(connector: ShoperConnector) -> None:
    created = await connector.create_product(ConnectorProduct(sku="SKU-5", name="Kubek"))
    uploaded = await connector.upload_image(created.external_id, "https://example.com/a.jpg")
    assert uploaded.url == "https://example.com/a.jpg"
    assert uploaded.external_id == created.external_id


async def test_transparently_reauthenticates_after_a_401_on_a_cached_token(
    connector: ShoperConnector, fake_api: FakeShoperAPI
) -> None:
    """Simulates the real token being invalidated server-side sooner than
    its stated expires_in - a single 401 should be absorbed by one
    automatic re-auth-and-retry rather than surfacing as a failure."""
    await connector.create_product(ConnectorProduct(sku="SKU-6", name="Plecak"))

    fake_api.reject_bearer_once = True
    products, _ = await connector.get_products()
    assert len(products) == 1


async def test_authenticates_once_per_connector_across_multiple_calls(
    connector: ShoperConnector, fake_api: FakeShoperAPI
) -> None:
    auth_calls = {"count": 0}
    original_handler = fake_api.handler

    def counting_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/webapi/rest/auth":
            auth_calls["count"] += 1
        return original_handler(request)

    connector._client._transport = httpx.MockTransport(counting_handler)

    await connector.get_products()
    await connector.get_products()
    await connector.get_categories()

    assert auth_calls["count"] == 1
