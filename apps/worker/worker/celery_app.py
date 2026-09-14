import os

from celery import Celery

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
    ],
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Populated in Phase 15 (Recommendations scheduler); empty for now.
    beat_schedule={},
)
