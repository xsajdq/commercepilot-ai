import uuid

import pytest
from cp_connectors.allegro import AllegroConnector
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


def test_unsupported_platform_raises() -> None:
    with pytest.raises(UnsupportedPlatformError):
        build_connector(_connection(ConnectionPlatform.SHOPER), {})


def test_missing_credentials_raise_key_error() -> None:
    with pytest.raises(KeyError):
        build_connector(_connection(ConnectionPlatform.WOOCOMMERCE), {})
