FROM python:3.13-slim AS base

# Build context is the repo root (not apps/worker): requirements.txt's
# `-e ../../packages/...` lines are resolved relative to the requirements
# file itself, so packages/ must already exist at that same relative
# position before pip install runs (same reasoning as apps/api/Dockerfile).
WORKDIR /repo

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY apps/worker/requirements.txt apps/worker/requirements.txt
COPY packages/shared packages/shared
COPY packages/domain packages/domain
COPY packages/connectors packages/connectors
COPY packages/sync packages/sync
RUN pip install -r apps/worker/requirements.txt

COPY apps/worker/worker apps/worker/worker

WORKDIR /repo/apps/worker

CMD ["celery", "-A", "worker.celery_app", "worker", "--loglevel=INFO"]
