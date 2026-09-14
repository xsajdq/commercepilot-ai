# Secret rotation (Phase 21)

Two secrets in this app can be rotated without downtime or forcing
every tenant to reconnect their stores or every user to re-login:
`ENCRYPTION_KEY` (connector credentials at rest) and `SECRET_KEY` (JWT
access token signing). Both follow the same shape - a "current +
previous" pair, verified/decrypted against both, written with only the
current one - rather than an arbitrary key list, because a rotation is
a two-state operation (before/after), not an open-ended history.

Everything else this app treats as a secret (`STRIPE_SECRET_KEY`,
`STRIPE_WEBHOOK_SECRET`, `ANTHROPIC_API_KEY`, database/Redis
credentials) rotates the ordinary way any config value does: update it
and redeploy. Nothing in this app persists data *encrypted with* or
*signed by* those, so there's no migration step - only `ENCRYPTION_KEY`
and `SECRET_KEY` need this two-phase dance.

## Rotating `ENCRYPTION_KEY`

Protects `Connection.encrypted_credentials` (`cp_shared.crypto`, a
`cryptography.fernet.MultiFernet` under the hood - see that module's
own docstring).

1. Generate a new key: `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
2. Deploy with `ENCRYPTION_KEY` set to the new key and
   `ENCRYPTION_KEY_PREVIOUS` set to the *old* `ENCRYPTION_KEY` value.
   From this point: new/updated connections encrypt under the new key;
   existing rows (still under the old key) keep decrypting fine, since
   both apps/api and apps/worker now try both keys.
3. Run the migration task once against the running deployment:
   `celery -A worker.celery_app call worker.reencrypt_all_connections`
   (or trigger it any other way this app's task queue is normally
   driven). It reports `{"migrated": N, "failed": [...]}` - a non-empty
   `failed` list names `Connection` ids that could not be decrypted
   under *either* key, which needs investigating before continuing
   (each of those rows most likely predates whatever key is even in
   `ENCRYPTION_KEY_PREVIOUS` - a live rotation only pairs two keys at a
   time, so a row from an even older rotation would need its own step
   through the key it was actually written under).
4. Confirm `failed` is empty, then deploy again with
   `ENCRYPTION_KEY_PREVIOUS` removed entirely.

## Rotating `SECRET_KEY`

Protects the HS256 signature on access tokens
(`apps/api/app/core/security.py`). Refresh tokens are unaffected - they
are opaque, high-entropy strings (`secrets.token_urlsafe`), never JWTs,
and are looked up by their SHA-256 hash in the database, not verified
against `SECRET_KEY`.

1. Generate a new key: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`.
2. Deploy with `SECRET_KEY` set to the new value and
   `SECRET_KEY_PREVIOUS` set to the *old* `SECRET_KEY` value. New logins
   sign with the new key only; an access token issued before the
   rotation (signed under the old key) keeps verifying until it expires
   naturally (`ACCESS_TOKEN_EXPIRE_MINUTES`, 15 minutes by default) -
   nobody is force-logged-out mid-rotation.
3. Wait at least `ACCESS_TOKEN_EXPIRE_MINUTES` past the deploy in step 2
   - every token issued under the old key has now expired on its own.
4. Deploy again with `SECRET_KEY_PREVIOUS` removed.

## Why this needs its own runbook rather than "just redeploy"

Both secrets are read by data *already at rest* (an encrypted
credentials blob, an unexpired token) written before the rotation - a
naive "swap the env var and redeploy" would make every such row/token
instantly unreadable/invalid the moment the new deploy goes live. The
"current + previous" pair is what buys the overlap window to migrate or
let old data expire before removing the old key from config entirely.
