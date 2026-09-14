from cp_ai.tools.builtin.product_tools import (
    get_product_tool,
    request_listing_publish_tool,
    update_price_tool,
    update_product_content_tool,
)
from cp_ai.tools.registry import ToolRegistry


def register_builtin_tools(registry: ToolRegistry) -> None:
    """Registers every tool `cp_ai` ships out of the box. Agents (Phase 9+)
    call this once when they build their `ToolRegistry`."""
    registry.register(get_product_tool())
    registry.register(update_price_tool())
    registry.register(update_product_content_tool())
    registry.register(request_listing_publish_tool())


__all__ = [
    "get_product_tool",
    "register_builtin_tools",
    "request_listing_publish_tool",
    "update_price_tool",
    "update_product_content_tool",
]
