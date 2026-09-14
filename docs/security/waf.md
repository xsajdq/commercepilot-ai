# WAF (Phase 21)

Cloudflare sits in front of the whole stack for DNS/CDN/TLS (see
`infrastructure/hetzner/README.md`) and is this project's chosen WAF
layer - nothing here is code in this repo; it's Cloudflare account/zone
configuration, done once a real domain and Cloudflare zone exist. This
document exists so that setup isn't invented from memory when the time
comes, and so the two layers this repo *does* implement
(`apps/api/app/core/security_headers.py` +
`apps/api/app/core/rate_limit.py`, and the proxy-layer Traefik
middleware in `infrastructure/traefik/dynamic/security.yml`) are
understood as defense in depth *underneath* Cloudflare, not a
replacement for it.

## What to enable in the Cloudflare dashboard

- **Managed WAF ruleset** (Cloudflare Managed Rules) - on for the whole
  zone. Catches the standard OWASP-class attack signatures (SQLi, XSS,
  path traversal, known scanner/bot signatures) before they ever reach
  Traefik or apps/api.
- **Rate limiting rules** - a zone-level rule on `/auth/*` tighter than
  apps/api's own per-IP limiter (e.g. block an IP outright for 10
  minutes after 30 requests/minute to `/auth/*`) - Cloudflare's own
  limiter runs at the edge, before a request even reaches the origin
  server, so it stops a flood apps/api's Redis-backed limiter would
  still have to spend a connection to reject.
- **Bot Fight Mode** (or Super Bot Fight Mode on a paid plan) - targets
  the credential-stuffing/scraping bots most likely to hit `/auth/*`
  and the product-catalog read endpoints.
- **"I'm Under Attack" mode** - not a standing setting; an incident
  response tool to reach for during an active volumetric attack (adds a
  JS challenge in front of every request). Document this in the
  on-call runbook once one exists (Phase 21/22 territory), so it isn't
  something someone has to discover live during an incident.
- **Always Use HTTPS** + **Automatic HTTPS Rewrites** - Traefik's own
  HSTS header (`infrastructure/traefik/dynamic/security.yml`) only
  protects a browser that has already visited once over HTTPS; this
  Cloudflare setting protects the very first visit too.

## What this does *not* replace

- **Tenant isolation** - a WAF has no concept of this app's tenant
  model; it can't tell a validly-authenticated cross-tenant request
  from a legitimate one. That's `apps/api/app/auth/dependencies.py`'s
  job (see `docs/security/README.md`), unaffected by anything here.
- **Prompt injection defenses** - a WAF filters HTTP requests, not text
  an already-authorized AI agent reads out of a product description or
  review. See `docs/security/README.md`'s own section on this.
- **Application-level rate limiting** - Cloudflare's rate limiting
  rules are IP/URL-pattern based and don't know this app's tenant or
  plan; `apps/api/app/core/rate_limit.py` and (once billing enforces
  it) `cp_billing`'s AI budget guard are still the only things that
  understand "this tenant's own limit," not just "this IP's."
