# Observability stack (Phase 21)

Local Prometheus + Grafana, wired to the real metrics `apps/api` and
`apps/worker` already expose (see `apps/api/app/core/metrics.py` and
`apps/worker/worker/observability.py`).

## Running it

Kept behind a compose profile so a plain `docker compose up` (the
default local dev loop) stays lightweight - opt in explicitly:

```bash
docker compose --profile observability up prometheus grafana
```

- Prometheus: http://localhost:9090
- Grafana: http://localhost:3001 (default login `admin` / `admin` - the
  local-only default `GF_SECURITY_ADMIN_PASSWORD` in `docker-compose.yml`;
  set a real one via `.env` for anything beyond a laptop)

Grafana auto-provisions the Prometheus datasource
(`grafana/provisioning/datasources/prometheus.yml`) and the
"CommercePilot" dashboard (`grafana/dashboards/commercepilot.json`) on
startup - nothing to click through manually.

## What the dashboard shows

- API request rate by route + status
- API p95 latency by route
- API 5xx error rate
- Celery task throughput by task name + status
- Celery task failure count (last 15 minutes)
- Celery task p95 duration by task name

These are exactly the metrics `docs/architecture/deployment.md`'s
"Monitoring" section named as the starting dashboard - API latency,
Celery queue/failure signal, and per-task health. CPU/RAM/disk and
PostgreSQL/Redis health (also named there) aren't wired up yet: they'd
come from `node_exporter`/`postgres_exporter`/`redis_exporter` sidecars,
which is real additional infrastructure this repo doesn't run anywhere
yet (there's no deployed host to install `node_exporter` on) - tracked
honestly as a gap rather than faked with a stub panel.

## Alerting

Not implemented: an actual alert (paging, Slack, email) needs an
Alertmanager instance and somewhere to send notifications, neither of
which exist in this repo yet. `docs/architecture/deployment.md`'s
threshold list (queue length, CPU, disk, failed jobs, AI cost) is the
starting point once that infrastructure exists - don't wire alert rules
against thresholds nobody has calibrated against real traffic yet.

## Why Celery needs `PROMETHEUS_MULTIPROC_DIR`

Celery's default `prefork` pool runs every task in a forked child
process, not the parent - a plain in-memory `prometheus_client.Counter`
would only ever see the parent's own untouched counters. Multiprocess
mode (`prometheus_client.multiprocess`) is the library's documented
answer: each process writes its values to its own file under
`PROMETHEUS_MULTIPROC_DIR`, and only the parent (via the `worker_init`
signal, which fires once before any child forks) starts the actual
metrics HTTP server, backed by a `MultiProcessCollector` that merges
every file at scrape time. See `apps/worker/worker/observability.py`'s
own docstring for the full reasoning - verified for real by running a
live `celery worker --concurrency=2` and confirming `celery_task_total`
correctly aggregated task outcomes across both forked children.
