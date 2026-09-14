import pytest
from httpx import AsyncClient

from app.core.config import get_settings

pytestmark = pytest.mark.asyncio(loop_scope="session")


class TestRateLimitMiddleware:
    async def test_health_is_never_rate_limited(self, client: AsyncClient, monkeypatch) -> None:
        settings = get_settings()
        monkeypatch.setattr(settings, "rate_limit_default_per_minute", 1)

        for _ in range(5):
            result = await client.get("/health")
            assert result.status_code == 200

    async def test_auth_endpoints_get_a_tighter_limit(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        settings = get_settings()
        monkeypatch.setattr(settings, "rate_limit_auth_per_minute", 3)

        payload = {
            "email": "ratelimit-test@example.com",
            "password": "supersecret123",
            "full_name": "Rate Limit Test",
            "tenant_name": "Rate Limit Shop",
        }

        # First request succeeds; the next two fail for an ordinary
        # reason (duplicate email) but still count against the limit -
        # the limiter runs before the route even executes.
        first = await client.post("/auth/register", json=payload)
        assert first.status_code == 201
        second = await client.post("/auth/register", json=payload)
        assert second.status_code == 409
        third = await client.post("/auth/register", json=payload)
        assert third.status_code == 409

        fourth = await client.post("/auth/register", json=payload)

        assert fourth.status_code == 429
        assert "Retry-After" in fourth.headers
        assert fourth.json()["detail"] == "Too many requests"

    async def test_non_auth_routes_use_the_default_limit(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        settings = get_settings()
        monkeypatch.setattr(settings, "rate_limit_default_per_minute", 2)

        first = await client.get("/connections", headers={"Authorization": "Bearer bogus"})
        second = await client.get("/connections", headers={"Authorization": "Bearer bogus"})
        third = await client.get("/connections", headers={"Authorization": "Bearer bogus"})

        assert first.status_code == 401
        assert second.status_code == 401
        assert third.status_code == 429

    async def test_different_client_ips_are_tracked_independently(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        settings = get_settings()
        monkeypatch.setattr(settings, "rate_limit_auth_per_minute", 1)

        first_ip_headers = {"X-Forwarded-For": "1.1.1.1"}
        second_ip_headers = {"X-Forwarded-For": "2.2.2.2"}

        blocked = await client.get("/auth/tenants", headers=first_ip_headers)
        assert blocked.status_code in (401, 429)
        again_blocked = await client.get("/auth/tenants", headers=first_ip_headers)
        assert again_blocked.status_code == 429

        # A different (forwarded-for) IP has its own, untouched budget.
        other_ip = await client.get("/auth/tenants", headers=second_ip_headers)
        assert other_ip.status_code != 429
