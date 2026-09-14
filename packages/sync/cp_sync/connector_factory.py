from typing import Any

from cp_connectors.allegro import AllegroConnector
from cp_connectors.base import CommerceConnector
from cp_connectors.idosell import IdoSellConnector
from cp_connectors.prestashop import PrestaShopConnector
from cp_connectors.shoper import ShoperConnector
from cp_connectors.woocommerce import WooCommerceConnector
from cp_domain.connection import Connection, ConnectionPlatform


class UnsupportedPlatformError(Exception):
    """Raised for a platform with no connector implementation at all.
    Every ConnectionPlatform now has one (IdoSellConnector, the last,
    landed in Phase 19) - this stays in place for whatever platform
    joins the enum next."""


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
    if connection.platform == ConnectionPlatform.SHOPER:
        return ShoperConnector(
            store_url=credentials["store_url"],
            client_id=credentials["client_id"],
            client_secret=credentials["client_secret"],
        )
    if connection.platform == ConnectionPlatform.PRESTASHOP:
        return PrestaShopConnector(
            store_url=credentials["store_url"],
            api_key=credentials["api_key"],
        )
    if connection.platform == ConnectionPlatform.IDOSELL:
        return IdoSellConnector(
            store_url=credentials["store_url"],
            api_key=credentials["api_key"],
        )

    raise UnsupportedPlatformError(
        f"no connector implemented for platform {connection.platform!r}"
    )
