# Pilot onboarding guide (Phase 22)

For whoever is on the call (or Slack thread) with a pilot merchant
walking them through their first connection. Written from the merchant's
side of the screen - what they actually see and click - not from the
connector's internals; see `docs/connectors/README.md` for the
implementation side of each platform.

## Before the call

1. Confirm the merchant has an active account (`/register` on the app,
   or you've created one for them) and can log in.
2. Know which platform they're on - the credential steps below are
   different for each, and per Phase 22b the app now shows contextual
   help text for whichever platform is selected on the Connections page,
   but it's worth having the steps ready yourself too.
3. **Never ask for or type a merchant's credentials into anything but the
   app's own "Add a connection" form.** Not Slack, not email, not a
   shared doc - CLAUDE.md's "never store API credentials in plaintext"
   starts with never having them pass through anything that isn't
   already encrypting them (`app/core/crypto.py`, Fernet, at rest).

## What happens after they click "Add connection"

This is worth explaining to the merchant up front, since Phase 22a
changed the actual behavior here: submitting the form creates the
connection immediately (it shows up in the table right away), but a
real check against their store runs in the background within a few
seconds - the exact same check `worker.test_connection`
(`apps/worker/worker/tasks/connection_health.py`) also re-runs every
time someone clicks "Test connection" on an existing row. If the
credentials are wrong, the row's status flips to `error` with a
specific reason (bad credentials vs. store unreachable vs. something
else) instead of silently staying "connected" until the next scheduled
sync fails a day later. Tell them to refresh the page after ~5 seconds
if the status still says "connected" but they're not confident it took.

## Per-platform credential steps

### WooCommerce

The connection needs `store_url`, `consumer_key`, `consumer_secret`.

1. WordPress admin → **WooCommerce → Settings → Advanced → REST API**.
2. **Add key.** Description can be anything (e.g. "CommercePilot").
3. Permissions: **Read/Write** (a future phase that publishes listing
   changes needs write access even though today's sync is read-heavy -
   see CLAUDE.md's control-flow: every write still goes through
   Validation → Policy → Risk → Approval regardless of what the API key
   itself is capable of).
4. Copy the **Consumer key** and **Consumer secret** shown immediately
   after creation - WooCommerce does not show the secret again.
5. Store URL is their site's root URL (e.g. `https://mystore.com`), not
   the `/wp-json/...` path - the connector appends that itself.

### Allegro

The connection needs a single `access_token`.

1. Allegro Developer Portal (apps.developer.allegro.pl) → register (or
   reuse) an app, then generate an access token for it via Allegro's
   OAuth2 device-code flow.
2. Tokens expire - a merchant testing this for the first time should
   know a `connected` status today doesn't guarantee it stays that way
   next week without a refresh flow in place (this repo's
   `allegro_oauth.py` implements the OAuth2 module; token refresh
   automation for long-lived connections is not yet wired into the
   Connections UI - flag this explicitly rather than let them assume
   otherwise).

### Shoper

The connection needs `store_url`, `client_id`, `client_secret`.

1. Shoper admin panel → **Ustawienia → API** (Settings → API).
2. Create a new API application/client - Shoper issues a client
   id/secret pair for OAuth2 client-credentials, which
   `ShoperConnector._authenticate` exchanges for a short-lived access
   token automatically on every sync (the merchant never sees or
   manages that token themselves).

### PrestaShop

The connection needs `store_url`, `api_key`.

1. PrestaShop admin → **Advanced Parameters → Webservice**.
2. Enable the webservice if it's off, then **Add a new key** - give it
   read access at minimum to the resources being synced (products,
   stock, orders).

### IdoSell

The connection needs `store_url`, `api_key`. IdoSell is a **read-only,
limited** connector today (the Connections page platform selector says
so explicitly) - a pilot merchant on IdoSell should be told upfront that
sync happens but no write-back (price/listing publish) is available yet.

1. IdoSell panel → **Ustawienia → Klucze API** (Settings → API keys).
2. Generate a key with catalog read access.

## If something goes wrong on the call

- **Status shows `error` right after adding the connection**: read the
  message under the connection row (or the tenant's own `last_error`
  field) out loud to the merchant - it's specifically a "check your
  credentials" auth message vs. a different failure, from the real
  pre-flight check, not a generic "something broke."
- **Nothing happens after clicking "Add connection"**: check the
  browser console/network tab for a 4xx from `POST /connections` before
  assuming the worker is stuck - a duplicate connection name 409s
  immediately and has nothing to do with credentials.
- **Still stuck**: escalate per `docs/operations/support-runbook.md` -
  don't guess at a live merchant's credentials or start improvising
  workarounds outside the documented connector setup.
