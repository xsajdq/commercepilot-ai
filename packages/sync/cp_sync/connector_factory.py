from typing import Any

from cp_connectors.allegro import AllegroConnector
from cp_connectors.base import CommerceConnector
from cp_connectors.woocommerce import WooCommerceConnector
from cp_domain.connection import Connection, ConnectionPlatform


class UnsupportedPlatformError(Exception):
    """Raised for a platform with no connector implementation yet
    (Shoper, PrestaShop, IdoSell - Phases 17-19)."""


def build_connector(connection: Connection, credentials: dict[str, Any]) -> CommerceConnector:
    """Instantiates the right connector for `connection.platform`, using
    the already-decrypted `credentials` dict (never pass an encrypted
    blob here - decrypt it first via cp_shared.crypto.decrypt_credentials).
    """
    if connection.platform == ConnectionPlatform.WOOCOMMERCE:
        return WooCommerceConnector(
            store_url=credentials["store_url"],
            consumer_key=credentials["consumer_key"],
            consumer_secret=credentials["consumer_secret"],
        )
    if connection.platform == ConnectionPlatform.ALLEGRO:
        return AllegroConnector(access_token=credentials["access_token"])

    raise UnsupportedPlatformError(
        f"no connector implemented for platform {connection.platform!r}"
    )
