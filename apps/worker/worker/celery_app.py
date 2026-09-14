import os

from celery import Celery
from celery.schedules import crontab

redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")

app = Celery(
    "commercepilot",
    broker=redis_url,
    backend=redis_url,
    include=[
        "worker.tasks.health",
        "worker.tasks.sync",
        "worker.tasks.pricing",
        "worker.tasks.product_content",
        "worker.tasks.listing",
        "worker.tasks.catalog",
        "worker.tasks.analytics",
        "worker.tasks.scheduler",
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
