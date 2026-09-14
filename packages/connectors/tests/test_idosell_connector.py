import httpx
import pytest
import pytest_asyncio

from cp_connectors.exceptions import (
    ConnectorAuthError,
    ConnectorError,
    ConnectorNotFoundError,
    ConnectorRateLimitError,
)
from cp_connectors.idosell import IdoSellConnector
from cp_connectors.types import ConnectorProduct, PriceUpdate, StockUpdate


class FakeIdoSellAPI:
    """A minimal in-memory stand-in for an IdoSell store's Admin API v3,
    driven through httpx.MockTransport - no real store, no network. The
    real response envelope shape was never confirmed (see
    IdoSellConnector's docstring), so this fake deliberately uses an
    arbitrary, differently-named envelope key per resource to prove the
    connector's "first list found" detection doesn't depend on guessing
    the real key name."""

    def __init__(self, *, api_key: str = "key_test") -> None:
        self.api_key = api_key
        self.products: list[dict] = []
        self.categories: list[dict] = [{"categoryId": 5, "someOtherField": "whatever"}]
        self.rate_limited_once = False
        self.error_once_with_status: int | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.headers.get("X-Api-Key") != self.api_key:
            return httpx.Response(401, json={"errors": [{"faultString": "invalid key"}]})

        if self.rate_limited_once:
            self.rate_limited_once = False
            return httpx.Response(429, headers={"Retry-After": "5"}, json={"error": "slow down"})
        if self.error_once_with_status is not None:
            status = self.error_once_with_status
            self.error_once_with_status = None
            return httpx.Response(status, json={"error": "server exploded"})

        path = request.url.path
        query = dict(httpx.QueryParams(request.url.query))

        if path == "/api/admin/v3/products/products/search":
            if "ids" in query:
                wanted = query["ids"]
                matches = [p for p in self.products if str(p.get("productId")) == wanted]
                return httpx.Response(200, json={"resultsList": matches})
            page = int(query.get("result_page", 1))
            limit = int(query.get("result_limit", 50))
            start = (page - 1) * limit
            return httpx.Response(
                200, json={"resultsList": self.products[start : start + limit]}
            )
        if path == "/api/admin/v3/products/categories":
            return httpx.Response(200, json={"categoriesList": self.categories})

        return httpx.Response(404, json={"error": "unhandled route"})


@pytest.fixture
def fake_api() -> FakeIdoSellAPI:
    return FakeIdoSellAPI()


@pytest_asyncio.fixture
async def connector(fake_api: FakeIdoSellAPI):
    client = httpx.AsyncClient(
        base_url="https://shop.example.com/api/admin/v3",
        headers={"X-API-KEY": fake_api.api_key},
        transport=httpx.MockTransport(fake_api.handler),
    )
    conn = IdoSellConnector(
        store_url="https://shop.example.com", api_key=fake_api.api_key, client=client
    )
    yield conn
    await conn.aclose()


@pytest_asyncio.fixture
async def bad_connector(fake_api: FakeIdoSellAPI):
    client = httpx.AsyncClient(
        base_url="https://shop.example.com/api/admin/v3",
        headers={"X-API-KEY": "wrong"},
        transport=httpx.MockTransport(fake_api.handler),
    )
    conn = IdoSellConnector(store_url="https://shop.example.com", api_key="wrong", client=client)
    yield conn
    await conn.aclose()


async def test_invalid_api_key_raises_connector_auth_error(bad_connector) -> None:
    with pytest.raises(ConnectorAuthError):
        await bad_connector.get_products()


async def test_get_products_extracts_real_ids_from_an_unknown_envelope_key(
    connector: IdoSellConnector, fake_api: FakeIdoSellAPI
) -> None:
    fake_api.products = [{"productId": 1}, {"productId": 2}, {"productId": 3}]

    products, cursor = await connector.get_products(limit=50)

    assert [p.external_id for p in products] == ["1", "2", "3"]
    assert cursor is None


async def test_get_products_fields_beyond_id_are_honestly_blank(
    connector: IdoSellConnector, fake_api: FakeIdoSellAPI
) -> None:
    fake_api.products = [{"productId": 42}]

    products, _ = await connector.get_products()

    assert products[0].external_id == "42"
    assert products[0].sku == ""
    assert products[0].name == ""
    assert products[0].price is None
    assert products[0].stock_quantity is None


async def test_pagination_walks_every_product_exactly_once(
    connector: IdoSellConnector, fake_api: FakeIdoSellAPI
) -> None:
    fake_api.products = [{"productId": i} for i in range(5)]

    seen: list[str] = []
    cursor: str | None = None
    for _ in range(10):
        page, cursor = await connector.get_products(cursor=cursor, limit=2)
        seen.extend(p.external_id for p in page)
        if cursor is None:
            break

    assert len(seen) == 5
    assert len(set(seen)) == 5


async def test_get_product_found(connector: IdoSellConnector, fake_api: FakeIdoSellAPI) -> None:
    fake_api.products = [{"productId": 7}]
    product = await connector.get_product("7")
    assert product.external_id == "7"


async def test_get_unknown_product_raises_not_found(connector: IdoSellConnector) -> None:
    with pytest.raises(ConnectorNotFoundError):
        await connector.get_product("999")


async def test_get_categories_extracts_ids_from_an_unknown_envelope_key(
    connector: IdoSellConnector,
) -> None:
    categories = await connector.get_categories()
    assert len(categories) == 1
    assert categories[0].external_id == "5"
    assert categories[0].name == ""


async def test_rate_limit_raises_with_retry_after(
    connector: IdoSellConnector, fake_api: FakeIdoSellAPI
) -> None:
    fake_api.rate_limited_once = True
    with pytest.raises(ConnectorRateLimitError) as exc_info:
        await connector.get_products()
    assert exc_info.value.retry_after_seconds == 5.0


async def test_server_error_raises_generic_connector_error(
    connector: IdoSellConnector, fake_api: FakeIdoSellAPI
) -> None:
    fake_api.error_once_with_status = 500
    with pytest.raises(ConnectorError):
        await connector.get_products()


async def test_get_category_parameters_is_always_empty(connector: IdoSellConnector) -> None:
    assert await connector.get_category_parameters("5") == []


@pytest.mark.parametrize(
    "call",
    [
        lambda c: c.create_product(ConnectorProduct(sku="X", name="Y")),
        lambda c: c.update_product("1", ConnectorProduct(sku="X", name="Y")),
        lambda c: c.update_price(PriceUpdate(external_id="1", price="10.00")),
        lambda c: c.update_stock(StockUpdate(external_id="1", quantity=1)),
        lambda c: c.upload_image("1", "https://example.com/a.jpg"),
        lambda c: c.publish_offer("1"),
    ],
)
async def test_write_operations_are_not_implemented(connector: IdoSellConnector, call) -> None:
    with pytest.raises(ConnectorError, match="does not implement"):
        await call(connector)
