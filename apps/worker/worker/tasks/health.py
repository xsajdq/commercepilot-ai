from worker.celery_app import app


@app.task(name="worker.ping")
def ping() -> str:
    """Sanity task used to verify the worker is consuming from the queue."""
    return "pong"
