# Support runbook (Phase 22)

For triaging a pilot merchant's "something's wrong" report. Written
around the tools that actually exist today - the read-only platform
admin views (Phase 22c/22d) and the Phase 21 observability stack - not
an idealized support process with tooling this repo hasn't built.

## First: get access

Support/on-call needs a user with `is_platform_admin = true`
(`apps/api/app/db/models/user.py`). There is deliberately no
self-service way to grant this - CONTRIBUTING.md's tenant-isolation
principles mean this is a bolt-on, audited-by-being-rare capability,
not a normal app feature. Promote a user directly in Postgres:

```sql
UPDATE users SET is_platform_admin = true WHERE email = 'support@yourteam.example';
```

That user's session then sees an **Admin** entry in the sidebar and can
read (never write) `/admin/tenants` and `/admin/tenants/{id}` - see
`apps/api/app/api/routes/admin.py`. Every route behind
`require_platform_admin` is read-only by construction: there is no
mutation endpoint under `/admin/*` at all, so there is no risk of a
support session accidentally acting *as* the tenant. If a fix requires
changing that tenant's own data, it happens through their own session
(ask them to do it on the call, or use a separate impersonation
capability if one is ever built - it isn't yet).

## Triage flow

### 1. Find the tenant

`/admin/tenants` lists every tenant with, at a glance: plan/subscription
status, member count, connection count (and how many are in `error`),
and the status of their most recent AI job. This is usually enough to
answer "is anything obviously on fire for this merchant" before you've
even opened their detail page. Sort by eye for anything with a red
"in error" connection count or a `failed` latest-AI-job badge.

### 2. Open the tenant detail page

`/admin/tenants/{id}` shows:

- **Members** - who has access, and their role. Useful for "can you
  check with your teammate who set this up" style questions.
- **Connections** - every connection's live status and `last_error`
  text (truncated in the UI; hover for the full string). This is the
  same `last_error` the merchant sees on their own Connections page -
  support isn't seeing anything the merchant couldn't also see
  themselves, just without needing the merchant to screen-share.
- **Recent AI jobs** - the last 10 `AIJob` rows (catalog audits,
  pricing/content/listing recommendations, dashboard narratives) with
  status and error message. A `failed` job's `error_message` is
  usually the fastest way to tell "the AI provider errored" from "a
  connector call inside the agent's tool failed" from "a policy/risk
  check rejected the action" - keep reading rather than guessing from
  the status alone.
- **Recent recommendations** - the last 10, with risk level and
  approval status. If a merchant says "I approved something and nothing
  happened," check whether it's still `pending_approval` (they didn't
  actually approve it), `executing` (in flight), or `failed` (approved,
  ran, and the execution itself errored - the audit log entry created
  for that recommendation execution, per CONTRIBUTING.md's "every mutation
  creates an audit log," is the next thing to check).

### 3. Cross-reference with observability (Phase 21)

The admin views show *what* is wrong for one tenant; Prometheus/Grafana
and Sentry (`docs/architecture/deployment.md`'s Monitoring section,
`infrastructure/observability/README.md`) show whether it's isolated to
them or systemic:

- A `failed` AI job for one tenant + a spike in Celery task failure
  rate for that task name in Grafana → likely a systemic issue (AI
  provider outage, a bad deploy) - stop debugging this one tenant and
  check recent deploys / provider status pages instead.
- A `failed` AI job for one tenant with nothing unusual in Grafana →
  probably tenant-specific (their store's data has something the agent
  didn't expect - e.g. a product with `UNKNOWN` cost the pricing agent
  can't safely price, per CONTRIBUTING.md rule #9). Sentry's stack trace for
  the specific job is the next step.
- Structured logs (`cp_shared.logging`, Phase 21a) are redaction-safe -
  they never contain access tokens, refresh tokens, API keys, or
  customer PII, so searching them by tenant_id or connection_id during
  triage is always safe, per CONTRIBUTING.md's "never log" list.

### 4. A connection is stuck in `error`

Walk the merchant through re-checking their credentials
(`docs/operations/pilot-onboarding.md` has the per-platform steps), then
have them click **Test connection** on that row - it re-runs the exact
same real pre-flight check (`worker.test_connection`) that runs
automatically when a connection is first created. Support cannot
trigger this on the merchant's behalf (there's no `/admin` mutation
route, by design), so this always ends with "ask the merchant to click
the button," not "fix it for them."

### 5. Something looks wrong with billing/usage

`/admin/tenants/{id}`'s plan/subscription badges come straight from
that tenant's `Subscription` row - the same source `GET /billing`
serves to the merchant themselves. There is no separate "true" number
support can see that the merchant can't; if the numbers look wrong,
it's a Stripe webhook/sync bug (`apps/api/app/api/routes/billing.py`),
not a display bug in the admin view.

## What this runbook explicitly does not cover

- **Impersonating a tenant to act on their behalf.** Doesn't exist.
  Every fix that requires a mutation happens in the tenant's own
  session, or waits for one to be built with its own approval/audit
  story - never as a quiet exception carved into `/admin/*`.
- **Editing data directly in Postgres to "fix" a merchant's account.**
  The one sanctioned direct-SQL exception is the `is_platform_admin`
  promotion above, done once per support hire, not as a general
  troubleshooting technique. Anything else bypasses the
  Validation → Policy → Risk → Approval → Audit Log chain CONTRIBUTING.md
  requires for every mutation - "it's just support fixing a bug" is not
  an exception to that.
- **A ticketing/paging system.** Out of scope for this phase - this
  runbook assumes whatever channel the pilot merchant used to reach you
  (email, Slack, a call) and ends there.
