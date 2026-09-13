# packages/connectors (`cp_connectors`)

The `CommerceConnector` `Protocol` every platform integration implements
(`get_products`, `get_product`, `create_product`, `update_product`,
`update_price`, `update_stock`, `get_categories`, `upload_image`), plus
its own DTOs (`ConnectorProduct`, `ConnectorCategory`, `PriceUpdate`,
`StockUpdate`, `UploadedImage`) and exception hierarchy
(`ConnectorError`, `ConnectorNotFoundError`, `ConnectorAuthError`,
`ConnectorRateLimitError`).

Deliberately has **no dependency on `cp_domain` or `cp_shared`** - a
connector talks to an external HTTP API, never to our database, and its
DTOs are not the domain model. The sync engine (Phase 6) is what maps
between a connector's `ConnectorProduct` and `cp_domain.Product`/`Variant`
rows. This keeps the promise in CLAUDE.md #16 literal: an agent calling
through this interface cannot know or care which platform - or even
whether there *is* a real platform - it's talking to.

`MockConnector` is an in-memory fake implementing the full interface,
used by this package's own tests (`tests/test_mock_connector.py`) and,
later, by the sync engine and AI tool tests - exactly the "interface +
mock connector, tested without any real store" Phase 3 calls for. The
first real implementation is WooCommerce (Phase 4), then Allegro
(Phase 5).

Run its tests standalone (no DB, no other services needed):

```bash
cd packages/connectors
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```
