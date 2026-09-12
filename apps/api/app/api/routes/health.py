from fastapi import APIRouter
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness check: the process is up. No dependency calls."""
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness() -> dict[str, object]:
    """Readiness check: verifies the API can reach Postgres and Redis."""
    settings = get_settings()
    checks: dict[str, str] = {}

    try:
        engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        await engine.dispose()
        checks["postgres"] = "ok"
    except Exception as exc:  # noqa: BLE001 - surface any connectivity failure
        checks["postgres"] = f"error: {exc}"

    try:
        redis = Redis.from_url(settings.redis_url, socket_connect_timeout=2)
        await redis.ping()
        await redis.aclose()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001 - surface any connectivity failure
        checks["redis"] = f"error: {exc}"

    status = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return {"status": status, "checks": checks}
