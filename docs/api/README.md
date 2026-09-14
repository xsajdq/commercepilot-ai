# API docs

FastAPI serves interactive OpenAPI docs at `/docs` in every environment
during development - that's the source of truth for exact request/
response shapes. This file covers the conventions that don't show up
there.

## Auth

Every route except `/health*` and `/auth/register`/`/auth/login`/
`/auth/refresh` requires `Authorization: Bearer <access_token>`. Access
tokens are short-lived (`ACCESS_TOKEN_EXPIRE_MINUTES`, default 15) and
carry both the user id (`sub`) and the currently-selected `tenant_id` -
every other route derives `tenant_id` from this token, never from a
client-supplied header, query param, or body field (CLAUDE.md #7). If a
user belongs to more than one tenant, `/auth/login` responds with
`requires_tenant_selection: true` and a list of memberships instead of a
token; the client re-calls `/auth/login` with a chosen `tenant_id`.
`/auth/switch-tenant` re-issues a token scoped to a different tenant the
user already belongs to.

## Error format

Errors are FastAPI's default `{"detail": "..."}` shape, with the status
code carrying the meaning:

- `401` - missing/invalid/expired token
- `403` - valid token, but no membership in the tenant it claims (or
  insufficient role, for role-gated routes)
- `404` - the resource doesn't exist *for this tenant* - a row that
  exists but belongs to another tenant looks identical to a row that
  doesn't exist at all, never a `403`, so a client can't use response
  codes to enumerate other tenants' resource ids
- `409` - a state conflict (duplicate SKU/connection name, or a decision
  attempted on a recommendation that isn't pending)

## Resources (Phase 6-12; auth is Phase 1)

- `/connections` - stores/marketplaces this tenant syncs from.
  `POST /connections/{id}/sync` enqueues `worker.sync_connection` and
  returns immediately with a `task_id` - sync itself always happens in
  the Celery worker, never inline in the request (CLAUDE.md #12/#13).
- `/products` - products and their offers. `POST /products` creates one
  manually (for testing without a live store); normally products arrive
  via a connection sync. `POST /products/{id}/generate-content-recommendation`,
  `POST /offers/{id}/generate-pricing-recommendation`, and
  `POST /offers/{id}/generate-listing-publish-recommendation` enqueue the
  product/pricing/listing agents (`worker.generate_product_content_recommendation`
  / `worker.generate_price_recommendation` /
  `worker.generate_listing_publish_recommendation`) - all three only ever
  *propose* a change into `/recommendations`, never mutate anything
  directly.
- `/recommendations` - everything an agent has proposed
  (`?status=pending_approval` etc. to filter). `POST .../approve` and
  `POST .../reject` are the only way a proposed change actually takes
  effect: approving resolves and runs the underlying tool call
  synchronously (a local DB write, not a slow external call for most
  tools, so this is fine to do inline - CLAUDE.md #13 is about
  long-running jobs, not every write) and writes a real `AuditEvent`;
  rejecting does nothing. Both are tenant-scoped and idempotent in
  effect - deciding an already-decided recommendation is a `409`, not a
  silent no-op. The one exception: approving a `listing_publish`
  recommendation only moves our own `Offer` to `pending` inline - the
  approve route then separately enqueues `worker.publish_listing_to_marketplace`,
  since *that* tool's whole point is a real network call to a
  marketplace, which does need to happen in the Celery worker, not the
  request handler.
- `/catalog` - the catalog agent. `POST /catalog/audit` enqueues
  `worker.run_catalog_audit`, which scans the *whole tenant's* catalog
  (not one product/offer) and records the run as an `AIJob`.
  `GET /catalog/audits` lists past runs, most recent first, with their
  full issue list. Most issues found are informational only (a missing
  price/EAN has no safe fix to propose); only an `ACTIVE` product with no
  offers anywhere becomes a real `catalog_fix` recommendation
  (archiving it) - see the roadmap's Phase 12 writeup for why.

No pagination yet - list endpoints cap at a fixed limit (200). Real
pagination is tracked as hardening work, not needed while there's no
production tenant with more rows than that.
