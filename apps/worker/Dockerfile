FROM python:3.13-slim AS base

# Build context is the repo root (not apps/worker): this image also needs
# packages/, which lives one level up from apps/worker.
WORKDIR /repo

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY apps/worker/requirements.txt apps/worker/requirements.txt
COPY packages/shared packages/shared
COPY packages/domain packages/domain
COPY packages/connectors packages/connectors
COPY packages/sync packages/sync
COPY packages/pricing packages/pricing
COPY packages/analytics packages/analytics
COPY packages/ai packages/ai
COPY packages/policies packages/policies
COPY packages/billing packages/billing
# requirements.txt's `-e ../../packages/...` lines are resolved relative
# to pip's current working directory, not the requirements file's own
# location - `cd` into apps/worker first so they land on packages/ above.
RUN cd apps/worker && pip install -r requirements.txt

COPY apps/worker/worker apps/worker/worker

WORKDIR /repo/apps/worker

# Prometheus metrics (Phase 21) - only the real `worker` command ever
# binds this (see worker/observability.py); `celery beat` never does.
EXPOSE 9808

CMD ["celery", "-A", "worker.celery_app", "worker", "--loglevel=INFO"]
