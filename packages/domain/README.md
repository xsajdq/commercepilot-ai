# packages/domain (`cp_domain`)

The platform-agnostic e-commerce domain model, built on `cp_shared`'s
`Base` and mixins: `Brand`, `Category`, `Product`, `Variant`,
`Connection`, `Offer`, `Price`, `Stock`, `Order`/`OrderItem`, `Review`,
`Recommendation`, `Approval`, `AuditEvent`, `AIJob`.

Notes on the shape of things:

- **Offer** is a `Variant` listed on one `Connection` (a store/marketplace
  account) - price and stock are channel-specific, so `Price` and `Stock`
  hang off the offer, one row each, holding the *current* value.
- Price/stock *history* isn't duplicated here - it lives in `AuditEvent`
  (written by the approval engine starting Phase 8), which is also the
  general-purpose "who changed what, when, why" ledger the whole app
  writes to.
- `Recommendation.entity_type`/`entity_id` is intentionally polymorphic
  (not a FK) since a recommendation can be about a `Product`, an `Offer`,
  or anything else added later.
- Missing manufacturer data (`ean`, `cost`, `vat_rate`, `weight_kg`, ...)
  is `NULL`, never guessed - per CLAUDE.md, an agent must never invent a
  technical spec.
- No REST endpoints yet - this phase is schema only. See
  `apps/api/tests/test_domain_models.py` for the ORM-level tests proving
  constraints, cascades, and tenant scoping.

Installed as an editable local package depending on `cp-shared` (pip
resolves it from the sibling `packages/shared` checkout, not PyPI - see
`apps/api/requirements.txt`).
