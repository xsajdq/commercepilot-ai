import redis.asyncio as redis

from app.core.config import get_settings


def get_redis_client() -> redis.Redis:
    """Deliberately NOT cached (unlike `celery_client.get_celery_client`):
    an async Redis connection is bound to whatever event loop is running
    when it first actually opens a socket, and this app's own test
    suite exercises two different loop lifecycles in the same process -
    the shared async `AsyncClient` fixture's session-scoped loop, and
    `test_health.py`'s plain synchronous `TestClient` (its own
    internally-managed loop). A cached client created under one would
    crash the moment the other reused it. `app/api/routes/health.py`'s
    own readiness check already sidesteps this the same way: build a
    fresh client, use it, close it - never held across a request
    boundary. One extra connection per call is the accepted cost."""
    settings = get_settings()
    return redis.from_url(settings.redis_url, decode_responses=True)
