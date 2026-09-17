from functools import lru_cache

from celery import Celery

from app.core.config import get_settings


@lru_cache
def get_celery_client() -> Celery:
    """A task producer, not a worker: apps/api enqueues background work
    by task name (CONTRIBUTING.md #12/#13 - never do it inline here) but never
    imports apps/worker's task modules directly - the two apps only
    share `packages/`, never each other's code."""
    settings = get_settings()
    return Celery(broker=settings.redis_url, backend=settings.redis_url)
