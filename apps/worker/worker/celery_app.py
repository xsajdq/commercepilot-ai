import os

from celery import Celery
from celery.schedules import crontab
from celery.signals import setup_logging
from cp_shared.logging import configure_logging

import worker.observability  # noqa: F401 - registers Sentry + Prometheus signal handlers

redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")


@setup_logging.connect
def _configure_worker_logging(**kwargs) -> None:
    """Fully replaces Celery's own logging setup (the documented way to
    opt out of it) with our JSON + secret-redacting configuration -
    otherwise Celery installs its own colorized text formatter that
    bypasses `RedactingFilter` entirely."""
    configure_logging(service_name="worker")

app = Celery(
    "commercepilot",
    broker=redis_url,
    backend=redis_url,
    include=[
        "worker.tasks.health",
        "worker.tasks.sync",
        "worker.tasks.connection_health",
        "worker.tasks.pricing",
        "worker.tasks.product_content",
        "worker.tasks.listing",
        "worker.tasks.catalog",
        "worker.tasks.analytics",
        "worker.tasks.scheduler",
        "worker.tasks.maintenance",
    ],
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Phase 15: two dispatcher tasks (worker.tasks.scheduler) fan out to
    # every other agent - sync gets an hour's head start over the
    # recommendation dispatch, a pragmatic staggering rather than a
    # guaranteed pipeline (see that module's own docstring for why).
    beat_schedule={
        "daily-sync": {
            "task": "worker.dispatch_daily_sync",
            "schedule": crontab(hour=1, minute=0),
        },
        "daily-recommendations": {
            "task": "worker.dispatch_daily_recommendations",
            "schedule": crontab(hour=2, minute=0),
        },
    },
)
