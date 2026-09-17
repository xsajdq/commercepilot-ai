# packages/sync (`cp_sync`)

Phase 6's sync engine: pulls products from a connected marketplace via a
`CommerceConnector` and upserts them into the `cp_domain` model, scoped to
one tenant/`Connection`. This is the layer that actually maps a
connector's `ConnectorProduct` onto `cp_domain.Product`/`Variant`/`Offer`/
`Price`/`Stock` - connectors (Phase 3-5) deliberately know nothing about
the domain model or the database.

## `cp_sync.retry`

`retry_with_backoff(fn, *, max_attempts=5, base_delay=1.0)` - a small
hand-rolled async retry helper (no new dependency; `tenacity` wasn't worth
adding for this). Exponential backoff with jitter; honors
`ConnectorRateLimitError.retry_after_seconds` when the platform tells us
how long to wait. `ConnectorAuthError`/`ConnectorNotFoundError` are never
retried (permanent failures); `ConnectorRateLimitError`, `ConnectorError`,
and `httpx.TransportError` are.

## `cp_sync.connector_factory`

`build_connector(connection, credentials) -> CommerceConnector` - the one
place that dispatches a `Connection.platform` to a concrete connector
class and constructs it from decrypted credentials. Every
`ConnectionPlatform` now has one (IdoSell joined in Phase 19, the last
of the five - note that `IdoSellConnector`'s own read coverage is
partial and every write method deliberately raises, see
`packages/connectors/README.md`) - `UnsupportedPlatformError` stays in
place for whatever platform joins the enum next. Never touches
encryption itself - the caller
(currently `apps/worker`) is responsible for decrypting
`Connection.encrypted_credentials` first via `cp_shared.crypto`.

## `cp_sync.products`

`sync_products(db, *, tenant_id, connection, connector, page_limit=50,
max_attempts=5, base_delay=1.0) -> SyncResult` - the orchestration
function:

- Pages through `connector.get_products()` (retried per-page with
  `retry_with_backoff`); a page fetch that exhausts its retries stops the
  sync early with `SyncResult.fatal_error` set, but every product already
  committed from earlier pages/pages stays committed.
- Upserts each product idempotently: `Product` matched by
  `(tenant_id, sku)`, `Variant` the same way (1:1 with `Product` until a
  connector exposes real variations), `Offer` by
  `(connection_id, variant_id)`, `Price`/`Stock` by `offer_id` - all
  already-unique columns from the Phase 2 schema, so re-running a sync
  never creates duplicates.
- Isolates partial failures **per item via a SAVEPOINT**
  (`async with db.begin_nested(): ...`), not a full session rollback. A
  bad item (e.g. a DB constraint violation) is recorded in
  `SyncResult.failures` without corrupting the shared `AsyncSession` for
  the next item in the loop - a full `await db.rollback()` here was tried
  first and reliably broke the *next* item's queries with SQLAlchemy's
  `MissingGreenlet` error, because it unwinds more of the async session's
  internal state than a single bad flush warrants. The nested-transaction
  fix is covered by
  `apps/api/tests/test_sync_products.py::test_partial_failure_does_not_block_other_products`.
- Always updates `connection.last_synced_at`/`last_error` at the end,
  clearing a previous error on a fully successful run.

Only product-level fields are synced (sku, name, description, ean, price,
stock, offer status) - category/brand resolution across platforms and
real product variants aren't modeled yet.

Offer status: each connector reports status in its own platform's
vocabulary (WooCommerce: `publish`/`draft`/`pending`/`private`; Allegro:
`active`/`inactive`), mapped to `cp_domain.offer.OfferStatus` by
`_STATUS_MAP` - an unrecognized string is left alone rather than guessed.
This exists (Phase 11) because the listing agent's readiness check
depends on `Offer.status` reflecting marketplace reality; before that, a
synced offer's status was fetched from the connector and silently
dropped, sitting at the column default forever.

Skuless products: WooCommerce (and other platforms) allow a product
with no SKU at all - real, especially older or imported, catalogs
routinely have some. `_upsert_product` matches `Product`/`Variant` by
`(tenant_id, sku)`, so before this fix, every skuless product fell back
to `sku=""` and collapsed onto the very first one synced - a store with
several skuless products would end up with exactly one row for all of
them combined, each sync overwriting the last (reported as "only 1
product ever gets synced" against a real WooCommerce store).
`_effective_sku` now derives a connector-scoped synthetic sku
(`noSKU-<connection>-<external_id>`) for these, keeping each one
distinct without inventing a real spec value (CONTRIBUTING.md #9 is about
customer-facing data, not this package's own internal matching key).

Tested via `apps/api/tests/test_sync_products.py` (DB-integration tests
against a real Postgres, reusing apps/api's test fixtures) rather than
this package's own `tests/` - `sync_products` needs a real `AsyncSession`
and schema to be meaningfully tested, which `packages/sync` doesn't own.

Run this package's own standalone tests (retry + connector factory, no
DB needed):

```bash
cd packages/sync
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```
