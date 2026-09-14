from httpx import AsyncClient

from app.core.config import get_settings
from app.core.sentry import configure_sentry


class TestMetricsEndpoint:
    async def test_is_reachable_without_authentication(self, client: AsyncClient) -> None:
        result = await client.get("/metrics")

        assert result.status_code == 200
        assert "text/plain" in result.headers["content-type"]

    async def test_records_a_counter_for_a_real_request(self, client: AsyncClient) -> None:
        await client.get("/health")

        result = await client.get("/metrics")

        body = result.text
        assert 'http_requests_total{method="GET"' in body
        assert "/health" in body

    async def test_the_metrics_endpoint_itself_is_not_counted(self, client: AsyncClient) -> None:
        await client.get("/metrics")

        result = await client.get("/metrics")

        assert 'path="/metrics"' not in result.text


class TestConfigureSentry:
    def test_is_a_no_op_without_a_configured_dsn(self) -> None:
        settings = get_settings()
        assert settings.sentry_dsn is None  # true for local dev/CI/test - nothing to init against

        configure_sentry(settings)  # must not raise
