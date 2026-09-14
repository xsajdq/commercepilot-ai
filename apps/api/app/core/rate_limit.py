"""Redis-backed rate limiting (Phase 21) - a fixed 60-second window per
client IP, counted with a single `INCR` + `EXPIRE` pair rather than a
sliding-window library: simple, correct, and consistent with this
codebase's preference for owning small pieces of infrastructure logic
directly (see `cp_sync`'s own retry helper) over reaching for another
dependency.

Client IP resolution trusts `X-Forwarded-For`'s first entry when
present, falling back to the direct TCP peer otherwise. This app always
sits behind Traefik in every real deployment (see docker-compose.yml
and infrastructure/traefik) which sets that header reliably - without
it, every request would appear to come from Traefik's own container IP
and the limit would apply to the whole deployment as if it were one
client. Honest limitation: a request that reaches this app directly
(bypassing Traefik) can forge `X-Forwarded-For` to dodge the limit -
low severity for what this defends (brute force / accidental hammering,
not an auth boundary), and the fix is a real deployment never exposing
apps/api directly to the internet, which is already the intended
topology.
"""

import time

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import get_settings
from app.core.redis_client import get_redis_client

_WINDOW_SECONDS = 60
_AUTH_PREFIX = "/auth"
_EXEMPT_PATHS = {"/health", "/metrics"}


def _client_ip(scope: Scope) -> str:
    for name, value in scope.get("headers", []):
        if name == b"x-forwarded-for":
            return value.decode("latin-1").split(",")[0].strip()
    client = scope.get("client")
    return client[0] if client else "unknown"


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in _EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        settings = get_settings()
        is_auth_path = scope["path"].startswith(_AUTH_PREFIX)
        limit = (
            settings.rate_limit_auth_per_minute
            if is_auth_path
            else settings.rate_limit_default_per_minute
        )

        allowed, retry_after = await _check_and_increment(
            client_ip=_client_ip(scope),
            bucket="auth" if is_auth_path else "default",
            limit=limit,
        )
        if not allowed:
            response = JSONResponse(
                {"detail": "Too many requests"},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


async def _check_and_increment(*, client_ip: str, bucket: str, limit: int) -> tuple[bool, int]:
    """Fixed-window counter: every request within the same 60s window
    increments one Redis key (auto-expiring so it never needs manual
    cleanup); the window resets cleanly at each minute boundary rather
    than sliding, a deliberate simplicity trade-off (a client can burst
    up to `limit` right at a window boundary and again right after) that
    matches this phase's "starting point, not yet traffic-calibrated"
    framing above.
    """
    window_start = _current_window_start()
    key = f"ratelimit:{bucket}:{client_ip}:{window_start}"

    client = get_redis_client()
    try:
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, _WINDOW_SECONDS)

        if count > limit:
            ttl = await client.ttl(key)
            return False, max(ttl, 1)
        return True, 0
    finally:
        await client.aclose()


def _current_window_start() -> int:
    now = int(time.time())
    return now - (now % _WINDOW_SECONDS)
