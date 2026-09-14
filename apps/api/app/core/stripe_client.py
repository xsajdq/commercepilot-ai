from types import ModuleType

import stripe

from app.core.config import get_settings


def get_stripe_client() -> ModuleType | None:
    """A seam, not a hardcoded call: tests monkeypatch this function
    (`app.api.routes.billing.get_stripe_client`) to inject a fake
    stand-in instead of hitting the real Stripe API - the same pattern
    `worker/tasks/*.py` use for `_get_provider()`.

    Returns the configured `stripe` module (its stable top-level
    `Customer` / `checkout.Session` / `billing_portal.Session` / `Webhook`
    resources) with `api_key` set, or `None` when no secret key is
    configured (local dev, CI, or before a tenant ever touches billing)
    so callers can degrade to a 503 instead of the SDK raising a
    confusing auth error. Not cached: `Settings` is itself cached, and
    re-reading `stripe.api_key` on every call is free - caching here
    would only make tests that flip the configured key mid-run harder to
    reason about."""
    settings = get_settings()
    if not settings.stripe_secret_key:
        return None
    stripe.api_key = settings.stripe_secret_key
    return stripe
