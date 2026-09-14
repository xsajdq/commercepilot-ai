FROM python:3.13-slim AS base

# Build context is the repo root (not apps/api): this image also needs
# alembic.ini and migrations/, which live one level up from apps/api, and
# migrations/env.py locates the `app` package relative to its own file
# path assuming this same apps/api/migrations layout - see its comment.
WORKDIR /repo

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY apps/api/requirements.txt apps/api/requirements.txt
COPY packages/shared packages/shared
COPY packages/domain packages/domain
COPY packages/pricing packages/pricing
COPY packages/analytics packages/analytics
COPY packages/ai packages/ai
COPY packages/policies packages/policies
COPY packages/billing packages/billing
# requirements.txt's `-e ../../packages/...` lines are resolved relative
# to pip's current working directory, not the requirements file's own
# location - `cd` into apps/api first so they land on packages/ above.
RUN cd apps/api && pip install -r requirements.txt

COPY apps/api/app apps/api/app
COPY alembic.ini alembic.ini
COPY migrations migrations

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD curl -f http://localhost:8000/health || exit 1

# Migrations run on every container start rather than as a separate step:
# there's no deploy pipeline yet (Phase 0/1), and `alembic upgrade head`
# is a safe no-op once the database is already at head.
CMD ["sh", "-c", "alembic upgrade head && cd apps/api && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
