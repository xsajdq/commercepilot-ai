from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_liveness() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_readiness_reports_dependency_status() -> None:
    """Without real Postgres/Redis reachable, this must degrade gracefully
    rather than raising - the endpoint itself must never crash."""
    response = client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "degraded"}
    assert set(body["checks"].keys()) == {"postgres", "redis"}
