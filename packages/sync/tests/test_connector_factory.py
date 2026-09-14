import uuid
from types import SimpleNamespace

import pytest
from cp_connectors.allegro import AllegroConnector
from cp_connectors.idosell import IdoSellConnector
from cp_connectors.prestashop import PrestaShopConnector
from cp_connectors.shoper import ShoperConnector
from cp_connectors.woocommerce import WooCommerceConnector
from cp_domain.connection import Connection, ConnectionPlatform

from cp_sync.connector_factory import UnsupportedPlatformError, build_connector


def _connection(platform: ConnectionPlatform) -> Connection:
    return Connection(platform=platform, name="Test", tenant_id=uuid.uuid4())


def test_build_woocommerce_connector() -> None:
    connector = build_connector(
        _connection(ConnectionPlatform.WOOCOMMERCE),
        {"store_url": "https://shop.example.com", "consumer_key": "ck", "consumer_secret": "cs"},
    )
    assert isinstance(connector, WooCommerceConnector)


def test_build_allegro_connector() -> None:
    connector = build_connector(_connection(ConnectionPlatform.ALLEGRO), {"access_token": "tok"})
    assert isinstance(connector, AllegroConnector)


def test_build_shoper_connector() -> None:
    connector = build_connector(
        _connection(ConnectionPlatform.SHOPER),
        {"store_url": "https://shop.example.pl", "client_id": "cid", "client_secret": "cs"},
    )
    assert isinstance(connector, ShoperConnector)


def test_build_prestashop_connector() -> None:
    connector = build_connector(
        _connection(ConnectionPlatform.PRESTASHOP),
        {"store_url": "https://shop.example.com", "api_key": "key123"},
    )
    assert isinstance(connector, PrestaShopConnector)


def test_build_idosell_connector() -> None:
    connector = build_connector(
        _connection(ConnectionPlatform.IDOSELL),
        {"store_url": "https://shop.example.com", "api_key": "key123"},
    )
    assert isinstance(connector, IdoSellConnector)


def test_unsupported_platform_raises() -> None:
    """Every real ConnectionPlatform now has a connector (IdoSell was
    the last, Phase 19) - this exercises the fallback branch for
    whatever platform joins the enum next, via a stand-in object rather
    than a real (now nonexistent) unsupported platform value."""
    fake_connection = SimpleNamespace(platform="not_a_real_platform")
    with pytest.raises(UnsupportedPlatformError):
        build_connector(fake_connection, {})


def test_missing_credentials_raise_key_error() -> None:
    with pytest.raises(KeyError):
        build_connector(_connection(ConnectionPlatform.WOOCOMMERCE), {})
