"""Sentry error tracking + Prometheus task metrics for the Celery worker
(Phase 21). Imported by `celery_app.py` before Celery itself starts, so
`PROMETHEUS_MULTIPROC_DIR` is set before `prometheus_client` is first
imported anywhere in this process - required for its multiprocess mode
to work at all.

Celery's default pool is `prefork`: the parent process forks N child
processes, and each *task* actually runs in a child, not the parent. A
plain in-memory `prometheus_client.Counter` would only ever see the
parent's own (empty) counters - `prometheus_client.multiprocess` is the
library's own documented answer to this (the same technique Gunicorn
uses): each process writes its metric values to its own mmapped file
under `PROMETHEUS_MULTIPROC_DIR`, and a `MultiProcessCollector` merges
every file at scrape time. The metrics HTTP server itself is started
only once, from the parent process via the `worker_init` signal (fires
before any child forks) - starting it from a forked child would crash
trying to bind the same port twice.
"""

import os
import shutil
import time

os.environ.setdefault("PROMETHEUS_MULTIPROC_DIR", "/tmp/commercepilot-worker-metrics")

import sentry_sdk  # noqa: E402
from celery.signals import (  # noqa: E402
    task_failure,
    task_postrun,
    task_prerun,
    worker_init,
    worker_process_shutdown,
)
from cp_shared.sentry import scrub_event  # noqa: E402
from prometheus_client import (  # noqa: E402
    CollectorRegistry,
    Counter,
    Histogram,
    multiprocess,
    start_http_server,
)
from sentry_sdk.integrations.celery import CeleryIntegration  # noqa: E402

TASK_COUNT = Counter(
    "celery_task_total", "Total Celery tasks processed", ["task_name", "status"]
)
TASK_DURATION = Histogram(
    "celery_task_duration_seconds", "Celery task duration in seconds", ["task_name"]
)

_task_start_times: dict[str, float] = {}


def get_sentry_dsn() -> str | None:
    return os.environ.get("SENTRY_DSN") or None


def get_metrics_port() -> int:
    return int(os.environ.get("METRICS_PORT", "9808"))


def _configure_sentry() -> None:
    dsn = get_sentry_dsn()
    if not dsn:
        return
    sentry_sdk.init(
        dsn=dsn,
        environment=os.environ.get("ENVIRONMENT", "development"),
        integrations=[CeleryIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=False,
        before_send=scrub_event,
    )


@task_prerun.connect
def _on_task_prerun(task_id=None, **kwargs) -> None:
    _task_start_times[task_id] = time.monotonic()


@task_postrun.connect
def _on_task_postrun(task_id=None, task=None, state=None, **kwargs) -> None:
    started = _task_start_times.pop(task_id, None)
    if task is None:
        return
    if started is not None:
        TASK_DURATION.labels(task_name=task.name).observe(time.monotonic() - started)
    TASK_COUNT.labels(task_name=task.name, status=state or "SUCCESS").inc()


@task_failure.connect
def _on_task_failure(sender=None, task_id=None, **kwargs) -> None:
    _task_start_times.pop(task_id, None)
    if sender is not None:
        TASK_COUNT.labels(task_name=sender.name, status="FAILURE").inc()


@worker_process_shutdown.connect
def _on_worker_process_shutdown(pid=None, **kwargs) -> None:
    multiprocess.mark_process_dead(pid or os.getpid())


def _start_metrics_server() -> None:
    multiproc_dir = os.environ["PROMETHEUS_MULTIPROC_DIR"]
    # Stale files from a previous run (a crashed process that never hit
    # `worker_process_shutdown`) would otherwise keep reporting a dead
    # pid's last values forever - clear the directory on every fresh
    # start of the parent process, mirroring Gunicorn's own documented
    # multiprocess setup.
    shutil.rmtree(multiproc_dir, ignore_errors=True)
    os.makedirs(multiproc_dir, exist_ok=True)

    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)
    start_http_server(get_metrics_port(), registry=registry)


@worker_init.connect
def _on_worker_init(**kwargs) -> None:
    _configure_sentry()
    _start_metrics_server()
