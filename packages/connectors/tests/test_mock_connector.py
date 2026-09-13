from decimal import Decimal

import pytest

from cp_connectors.base import CommerceConnector
from cp_connectors.exceptions import ConnectorNotFoundError
from cp_connectors.mock import MockConnector
from cp_connectors.types import (
    CategoryParameter,
    ConnectorCategory,
    ConnectorProduct,
    PriceUpdate,
    StockUpdate,
)


@pytest.fixture
def connector() -> MockConnector:
    return MockConnector(categories=[ConnectorCategory(external_id="cat-1", name="Shoes")])


def test_mock_connector_satisfies_the_protocol(connector: MockConnector) -> None:
    assert isinstance(connector, CommerceConnector)


async def test_create_then_get_product(connector: MockConnector) -> None:
    created = await connector.create_product(ConnectorProduct(sku="SKU-1", name="Shoe"))
    assert created.external_id is not None

    fetched = await connector.get_product(created.external_id)
    assert fetched.sku == "SKU-1"


async def test_get_unknown_product_raises_not_found(connector: MockConnector) -> None:
    with pytest.raises(ConnectorNotFoundError):
        await connector.get_product("does-not-exist")


async def test_update_price_and_stock(connector: MockConnector) -> None:
    created = await connector.create_product(ConnectorProduct(sku="SKU-2", name="Hat"))

    await connector.update_price(
        PriceUpdate(external_id=created.external_id, price=Decimal("29.99"))
    )
    await connector.update_stock(StockUpdate(external_id=created.external_id, quantity=5))

    fetched = await connector.get_product(created.external_id)
    assert fetched.price == Decimal("29.99")
    assert fetched.stock_quantity == 5


async def test_update_price_for_unknown_product_raises(connector: MockConnector) -> None:
    with pytest.raises(ConnectorNotFoundError):
        await connector.update_price(PriceUpdate(external_id="ghost", price=Decimal("1.00")))


async def test_update_stock_for_unknown_product_raises(connector: MockConnector) -> None:
    with pytest.raises(ConnectorNotFoundError):
        await connector.update_stock(StockUpdate(external_id="ghost", quantity=1))


async def test_update_product_for_unknown_id_raises(connector: MockConnector) -> None:
    with pytest.raises(ConnectorNotFoundError):
        await connector.update_product("ghost", ConnectorProduct(sku="X", name="X"))


async def test_pagination_walks_every_product_exactly_once(connector: MockConnector) -> None:
    for i in range(5):
        await connector.create_product(ConnectorProduct(sku=f"SKU-{i}", name=f"Product {i}"))

    seen: list[str] = []
    cursor: str | None = None
    for _ in range(10):  # bounded loop guards against an infinite-pagination bug
        page, cursor = await connector.get_products(cursor=cursor, limit=2)
        seen.extend(p.external_id for p in page)
        if cursor is None:
            break

    assert len(seen) == 5
    assert len(set(seen)) == 5


async def test_get_categories(connector: MockConnector) -> None:
    categories = await connector.get_categories()
    assert categories == [ConnectorCategory(external_id="cat-1", name="Shoes")]


async def test_upload_image_appends_to_product(connector: MockConnector) -> None:
    created = await connector.create_product(ConnectorProduct(sku="SKU-3", name="Bag"))

    uploaded = await connector.upload_image(created.external_id, "https://example.com/bag.jpg")
    assert uploaded.url == "https://example.com/bag.jpg"

    fetched = await connector.get_product(created.external_id)
    assert fetched.image_urls == ["https://example.com/bag.jpg"]


async def test_upload_image_for_unknown_product_raises(connector: MockConnector) -> None:
    with pytest.raises(ConnectorNotFoundError):
        await connector.upload_image("ghost", "https://example.com/x.jpg")


async def test_returned_dtos_are_copies_not_live_references(connector: MockConnector) -> None:
    """A caller mutating a DTO it received must never silently corrupt
    the connector's own state."""
    created = await connector.create_product(ConnectorProduct(sku="SKU-4", name="Cap"))

    created.name = "Mutated"

    fetched = await connector.get_product(created.external_id)
    assert fetched.name == "Cap"


async def test_publish_offer_sets_status_active(connector: MockConnector) -> None:
    created = await connector.create_product(ConnectorProduct(sku="SKU-5", name="Scarf"))
    assert created.status == "draft"

    await connector.publish_offer(created.external_id)

    fetched = await connector.get_product(created.external_id)
    assert fetched.status == "active"


async def test_publish_offer_for_unknown_product_raises(connector: MockConnector) -> None:
    with pytest.raises(ConnectorNotFoundError):
        await connector.publish_offer("ghost")


async def test_get_category_parameters_returns_configured_list() -> None:
    connector = MockConnector(
        category_parameters={
            "cat-1": [CategoryParameter(external_id="p1", name="Brand", required=True)]
        }
    )
    parameters = await connector.get_category_parameters("cat-1")
    assert parameters == [CategoryParameter(external_id="p1", name="Brand", required=True)]


async def test_get_category_parameters_for_unknown_category_returns_empty(
    connector: MockConnector,
) -> None:
    assert await connector.get_category_parameters("unknown-category") == []
