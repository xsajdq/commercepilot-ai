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
mock connector, tested without any real store" Phase 3 calls for.

`WooCommerceConnector` (Phase 4) is the first real implementation, against
WooCommerce's REST API v3 (`/wp-json/wc/v3`). Notes on its scope:

- Consumer Key/Secret auth over **HTTPS only** - WooCommerce requires
  OAuth1.0a request signing for plain HTTP instead, which isn't
  implemented here; connect stores over HTTPS.
- Each `ConnectorProduct` maps to one WooCommerce *simple* product;
  variable products (per-variation price/stock) aren't modeled yet.
- A product's categories are simplified to just the first one WooCommerce
  returns (`ConnectorProduct.category_external_id` is singular).
- `upload_image` works by rewriting the product's `images` array with the
  new URL appended - WooCommerce has no standalone upload-by-URL endpoint.
- Retry/backoff/rate-limit handling is **not** done here on purpose -
  errors are translated into typed exceptions
  (`ConnectorAuthError`/`ConnectorNotFoundError`/`ConnectorRateLimitError`/
  `ConnectorError`) and it's the sync engine's (Phase 6) job to decide how
  to react to them.

Tested against `tests/test_woocommerce_connector.py`'s `FakeWooCommerceAPI`
- an in-memory stand-in for the WooCommerce REST API driven through
  `httpx.MockTransport` - no real store, no new HTTP-mocking dependency.
  Allegro (Phase 5) is next.

Run its tests standalone (no DB, no other services needed):

```bash
cd packages/connectors
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```
