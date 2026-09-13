import itertools
import json
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio

from cp_connectors.allegro import AllegroConnector
from cp_connectors.exceptions import (
    ConnectorAuthError,
    ConnectorError,
    ConnectorNotFoundError,
    ConnectorRateLimitError,
)
from cp_connectors.types import ConnectorProduct, PriceUpdate, StockUpdate


class FakeAllegroAPI:
    """A minimal in-memory stand-in for Allegro's REST API, driven
    through httpx.MockTransport - no real seller account, no network."""

    def __init__(self) -> None:
        self.offers: dict[str, dict] = {}
        self.categories: list[dict] = [{"id": "cat-1", "name": "Shoes"}]
        self.category_parameters: dict[str, list[dict]] = {
            "cat-1": [
                {
                    "id": "p1",
                    "name": "Brand",
                    "required": True,
                    "dictionary": [{"id": "d1", "value": "Nike"}],
                }
            ]
        }
        self._offer_ids = itertools.count(1)
        self._image_ids = itertools.count(1)
        self.rate_limited_once = False
        self.error_once_with_status: int | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.headers.get("authorization") != "Bearer valid-token":
            return httpx.Response(401, json={"errors": [{"message": "invalid token"}]})

        if self.rate_limited_once:
            self.rate_limited_once = False
            return httpx.Response(429, headers={"Retry-After": "3"}, json={"errors": []})
        if self.error_once_with_status is not None:
            status = self.error_once_with_status
            self.error_once_with_status = None
            return httpx.Response(status, json={"errors": [{"message": "server exploded"}]})

        path, method = request.url.path, request.method

        if path == "/sale/categories" and method == "GET":
            return httpx.Response(200, json={"categories": self.categories})

        if path == "/sale/offers" and method == "GET":
            return self._list_offers(dict(httpx.QueryParams(request.url.query)))

        if path == "/sale/offers" and method == "POST":
            return self._create_offer(request)

        if path == "/sale/images" and method == "POST":
            image_id = next(self._image_ids)
            return httpx.Response(
                201, json={"location": f"https://allegroimg.example.com/img-{image_id}"}
            )

        if path.startswith("/sale/categories/") and path.endswith("/parameters"):
            category_id = path.split("/")[3]
            return httpx.Response(
                200, json={"parameters": self.category_parameters.get(category_id, [])}
            )

        if path.startswith("/sale/offers/") and method in ("GET", "PUT"):
            return self._offer_detail(path, method, request)

        return httpx.Response(404, json={"errors": [{"message": "unhandled route"}]})

    def _list_offers(self, query: dict[str, str]) -> httpx.Response:
        offset = int(query.get("offset", 0))
        limit = int(query.get("limit", 50))
        ids = sorted(self.offers, key=int)
        page_ids = ids[offset : offset + limit]
        return httpx.Response(
            200,
            json={"offers": [self.offers[i] for i in page_ids], "totalCount": len(ids)},
        )

    def _create_offer(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        offer_id = str(next(self._offer_ids))
        record = {"id": offer_id, "images": [], "parameters": [], **body}
        self.offers[offer_id] = record
        return httpx.Response(201, json=record)

    def _offer_detail(self, path: str, method: str, request: httpx.Request) -> httpx.Response:
        offer_id = path.rsplit("/", 1)[-1]
        if offer_id not in self.offers:
            return httpx.Response(404, json={"errors": [{"message": "not found"}]})
        if method == "GET":
            return httpx.Response(200, json=self.offers[offer_id])
        body = json.loads(request.content)
        self.offers[offer_id].update(body)
        return httpx.Response(200, json=self.offers[offer_id])


@pytest.fixture
def fake_api() -> FakeAllegroAPI:
    return FakeAllegroAPI()


@pytest_asyncio.fixture
async def connector(fake_api: FakeAllegroAPI):
    client = httpx.AsyncClient(
        base_url="https://api.allegro.pl",
        headers={"Authorization": "Bearer valid-token"},
        transport=httpx.MockTransport(fake_api.handler),
    )
    conn = AllegroConnector(access_token="valid-token", client=client)
    yield conn
    await conn.aclose()


@pytest_asyncio.fixture
async def bad_connector(fake_api: FakeAllegroAPI):
    client = httpx.AsyncClient(
        base_url="https://api.allegro.pl",
        headers={"Authorization": "Bearer wrong-token"},
        transport=httpx.MockTransport(fake_api.handler),
    )
    conn = AllegroConnector(access_token="wrong-token", client=client)
    yield conn
    await conn.aclose()


async def test_invalid_token_raises_connector_auth_error(bad_connector: AllegroConnector) -> None:
    with pytest.raises(ConnectorAuthError):
        await bad_connector.get_products()


async def test_create_then_get_product_is_a_draft(connector: AllegroConnector) -> None:
    created = await connector.create_product(
        ConnectorProduct(
            sku="SKU-1",
            name="Running Shoe",
            price=Decimal("149.00"),
            category_external_id="cat-1",
        )
    )
    assert created.external_id is not None
    assert created.status == "inactive"  # draft until published

    fetched = await connector.get_product(created.external_id)
    assert fetched.sku == "SKU-1"
    assert fetched.price == Decimal("149.00")
    assert fetched.category_external_id == "cat-1"


async def test_get_unknown_product_raises_not_found(connector: AllegroConnector) -> None:
    with pytest.raises(ConnectorNotFoundError):
        await connector.get_product("does-not-exist")


async def test_publish_offer_makes_it_active(connector: AllegroConnector) -> None:
    created = await connector.create_product(ConnectorProduct(sku="SKU-2", name="Hat"))
    assert created.status == "inactive"

    await connector.publish_offer(created.external_id)

    fetched = await connector.get_product(created.external_id)
    assert fetched.status == "active"


async def test_publish_offer_for_unknown_product_raises(connector: AllegroConnector) -> None:
    with pytest.raises(ConnectorNotFoundError):
        await connector.publish_offer("ghost")


async def test_update_price_and_stock(connector: AllegroConnector) -> None:
    created = await connector.create_product(ConnectorProduct(sku="SKU-3", name="Bag"))

    await connector.update_price(
        PriceUpdate(external_id=created.external_id, price=Decimal("59.99"))
    )
    await connector.update_stock(StockUpdate(external_id=created.external_id, quantity=12))

    fetched = await connector.get_product(created.external_id)
    assert fetched.price == Decimal("59.99")
    assert fetched.stock_quantity == 12


async def test_pagination_walks_every_offer_exactly_once(connector: AllegroConnector) -> None:
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


async def test_get_categories_returns_root_categories(connector: AllegroConnector) -> None:
    categories = await connector.get_categories()
    assert len(categories) == 1
    assert categories[0].external_id == "cat-1"
    assert categories[0].name == "Shoes"


async def test_get_category_parameters(connector: AllegroConnector) -> None:
    parameters = await connector.get_category_parameters("cat-1")
    assert len(parameters) == 1
    assert parameters[0].external_id == "p1"
    assert parameters[0].required is True
    assert parameters[0].dictionary_values == [{"id": "d1", "value": "Nike"}]


async def test_get_category_parameters_for_unknown_category_is_empty(
    connector: AllegroConnector,
) -> None:
    assert await connector.get_category_parameters("unknown") == []


async def test_create_product_with_category_parameters_round_trips(
    connector: AllegroConnector,
) -> None:
    created = await connector.create_product(
        ConnectorProduct(
            sku="SKU-4",
            name="Sneaker",
            category_external_id="cat-1",
            parameters={"p1": ["d1"]},
        )
    )
    fetched = await connector.get_product(created.external_id)
    assert fetched.parameters == {"p1": ["d1"]}


async def test_upload_image_hosts_on_allegro_then_appends(connector: AllegroConnector) -> None:
    created = await connector.create_product(ConnectorProduct(sku="SKU-5", name="Cap"))

    uploaded = await connector.upload_image(created.external_id, "https://example.com/cap.jpg")
    assert uploaded.url.startswith("https://allegroimg.example.com/")

    fetched = await connector.get_product(created.external_id)
    assert fetched.image_urls == [uploaded.url]


async def test_rate_limit_raises_with_retry_after(
    connector: AllegroConnector, fake_api: FakeAllegroAPI
) -> None:
    fake_api.rate_limited_once = True
    with pytest.raises(ConnectorRateLimitError) as exc_info:
        await connector.get_products()
    assert exc_info.value.retry_after_seconds == 3.0


async def test_server_error_raises_generic_connector_error(
    connector: AllegroConnector, fake_api: FakeAllegroAPI
) -> None:
    fake_api.error_once_with_status = 500
    with pytest.raises(ConnectorError):
        await connector.get_products()
