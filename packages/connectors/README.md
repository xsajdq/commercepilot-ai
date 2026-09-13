# packages/connectors (`cp_connectors`)

The `CommerceConnector` `Protocol` every platform integration implements
(`get_products`, `get_product`, `create_product`, `update_product`,
`update_price`, `update_stock`, `get_categories`, `upload_image`,
`get_category_parameters`, `publish_offer`), plus its own DTOs
(`ConnectorProduct`, `ConnectorCategory`, `CategoryParameter`,
`PriceUpdate`, `StockUpdate`, `UploadedImage`) and exception hierarchy
(`ConnectorError`, `ConnectorNotFoundError`, `ConnectorAuthError`,
`ConnectorRateLimitError`).

`get_category_parameters` and `publish_offer` exist because Allegro
(Phase 5) genuinely needs them - a marketplace offer belongs to a
category with its own mandatory attributes and goes through a distinct
draft-then-publish step, unlike a simple WooCommerce product. Platforms
without the concept implement them as a no-op / empty list rather than
omitting them, so callers (the sync engine) can always call both
regardless of which platform they're talking to.

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

`AllegroConnector` (Phase 5) is the second real implementation, against
Allegro's REST API (`api.allegro.pl`). Auth is OAuth2 Authorization Code -
`allegro_oauth.py` has `build_authorization_url` (redirect the seller to
for consent), `exchange_code_for_token`, and `refresh_access_token`
(Allegro tokens are short-lived, ~12h); `AllegroConnector` itself only
*uses* an already-issued Bearer token; a `ConnectorAuthError` from it most
likely means the token expired and the caller should refresh and retry
with a fresh connector instance, not treat it as permanent. Notes on
`AllegroConnector`'s scope:

- An offer belongs to exactly one category with its own mandatory
  parameters (`get_category_parameters`); values are set via
  `ConnectorProduct.parameters` (`{parameter_id: [value_id_or_text]}`).
- `create_product`/`update_product` always leave the offer as a draft
  (`publication.status=INACTIVE`) - `publish_offer` is the only path to
  making it live, matching Allegro's real create-then-publish flow.
- `get_categories` only returns Allegro's top-level categories - the real
  tree is deep and `CommerceConnector`'s generic signature has no way to
  request a specific parent's children.
- Delivery/shipping template assignment isn't modeled yet - a real
  production `create_product` call needs one and this doesn't send it.
- `upload_image` does Allegro's required two-step dance: POST the source
  URL to Allegro's own image host, then reference the returned
  Allegro-hosted URL on the offer.
- Offer descriptions are a structured "sections" rich-text format, not
  plain text, so `ConnectorProduct.description` round-trips as `None`.

Tested against `tests/test_allegro_connector.py`'s `FakeAllegroAPI` and
`tests/test_allegro_oauth.py`, both via `httpx.MockTransport` - no real
Allegro account, no sandbox credentials needed.

Run its tests standalone (no DB, no other services needed):

```bash
cd packages/connectors
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```
