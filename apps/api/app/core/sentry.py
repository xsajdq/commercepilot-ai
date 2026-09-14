import sentry_sdk
from cp_shared.sentry import scrub_event

from app.core.config import Settings


def configure_sentry(settings: Settings) -> None:
    """No-op when `SENTRY_DSN` isn't configured (local dev, CI, or
    before a real deployment sets one up) - error tracking is additive
    observability, never a hard dependency for the app to run.

    `send_default_pii` stays at its safe default (`False`); `before_send`
    is the same `cp_shared.sentry.scrub_event` used everywhere else, so
    an event never carries an access/refresh token, API key, or
    credential blob even if one ended up in a request header, a stack
    frame's local variables, or an `extra`/`tag` a caller attached.
    """
    if not settings.sentry_dsn:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        traces_sample_rate=0.1,
        send_default_pii=False,
        before_send=scrub_event,
    )
