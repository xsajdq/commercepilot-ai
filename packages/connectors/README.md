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

`ShoperConnector` (Phase 17) is the third real implementation, against
Shoper's REST API (`{store_url}/webapi/rest`). Network access to
`developers.shoper.pl` itself was blocked in the environment this was
built in, so its shape comes from Shoper's own indexed API reference
pages plus a third-party client library's resource names rather than
the OpenAPI spec directly - the class docstring marks each detail as
confirmed or inferred. Notes on its scope:

- Auth is `POST /webapi/rest/auth` with HTTP Basic (`client_id`,
  `client_secret`) returning a ~30-day bearer token with no refresh
  token - unlike `AllegroConnector`, this class performs that exchange
  itself and re-authenticates transparently (missing/expired cached
  token, or a live 401), so a caller only ever supplies
  `client_id`/`client_secret` (the same shape as WooCommerce's consumer
  key/secret), never a token.
- A product's name/description/active-flag live under a `translations`
  dict keyed by locale (Shoper stores are commonly multi-language) -
  this connector only reads/writes one locale (`pl_PL` by default) and
  doesn't attempt to keep every language in sync.
- `update_price`/`update_stock`/`publish_offer` read-then-write the
  relevant nested object (`stock`, or `translations[locale]`) instead of
  PUTting a bare partial fragment - price and stock quantity share one
  `stock` object, and name/description/active share one
  `translations[locale]` object, so a partial PUT risks the API
  full-replacing that nested object and dropping its siblings (unlike
  WooCommerce/Allegro, where every mutable field already has its own
  top-level key).
- `get_category_parameters` always returns `[]` (same documented
  limitation as `WooCommerceConnector` - no per-category mandatory-field
  concept was found) and `upload_image`'s exact request shape is a
  best-effort inference, flagged in the docstring for verification
  against a real store before production use.

Tested against `tests/test_shoper_connector.py`'s `FakeShoperAPI` via
`httpx.MockTransport` - no real Shoper store needed. Includes dedicated
tests for the two correctness risks its design exists to avoid (a price
update doesn't wipe stock quantity and vice versa) and for the
transparent-reauthentication behavior (one 401 on a cached token is
absorbed by a single re-auth-and-retry, and a connector instance only
authenticates once across multiple calls while its token stays valid).

`PrestaShopConnector` (Phase 18) is the fourth real implementation,
against PrestaShop's Webservice API (`{store_url}/api`) - confirmed
against PrestaShop's official developer docs, GitHub issues, and its own
published Postman collection (`PrestaShop/webservice-postman-examples`).
Notes on its scope:

- Auth is HTTP Basic with the webservice key as username and an empty
  password.
- Reads request `output_format=JSON`; a plain list request without
  `display=full` returns bare ids only, so this connector always passes
  `display=full`. Writes (POST/PUT/PATCH) always send an XML body
  regardless - PrestaShop 8.1+ can output JSON but cannot parse JSON
  *input*, and XML input works across every version, so this class never
  attempts JSON writes.
- Stock quantity is a genuinely separate architectural concern here, not
  just a risk to guard against: PrestaShop stores it in its own
  `stock_availables` resource keyed by `id_product` (one is
  auto-created alongside a new product), never on the product resource
  itself. `get_product`/`get_products` do a second lookup to merge it in;
  `update_stock`/`create_product`'s stock handling and
  `update_price`/`publish_offer`'s `PATCH` calls never touch each
  other's resource, so there's no equivalent of Shoper's shared-object
  risk to guard against - the separation is structural.
- Multi-language fields (`name`, `description`) are read/written for
  language id `"1"` only, the same "pick one locale" simplification as
  `ShoperConnector`'s `pl_PL` default.
- Image upload is `multipart/form-data` with the actual image bytes
  (fetched from the given URL first), not a URL reference - a third
  distinct image-handling strategy alongside WooCommerce's array-of-URLs
  and Allegro's fetch-then-reference two-step.
- `get_category_parameters` always returns `[]` (same documented
  limitation as WooCommerce/Shoper) and pagination uses the standard "a
  short page was the last page" rule rather than trusting an unconfirmed
  total-count header.

Tested against `tests/test_prestashop_connector.py`'s
`FakePrestaShopAPI` via `httpx.MockTransport` - the fake responds to
reads in JSON and parses writes as real XML (matching exactly what this
connector sends), including a small XML builder/parser round-trip for
the multi-language `<name><language id="1">...` shape.

Run its tests standalone (no DB, no other services needed):

```bash
cd packages/connectors
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```
