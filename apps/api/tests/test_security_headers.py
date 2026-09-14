from httpx import AsyncClient


class TestSecurityHeadersMiddleware:
    async def test_adds_hardening_headers_to_a_json_response(
        self, client: AsyncClient
    ) -> None:
        result = await client.get("/health")

        assert result.headers["x-content-type-options"] == "nosniff"
        assert result.headers["x-frame-options"] == "DENY"
        assert result.headers["referrer-policy"] == "strict-origin-when-cross-origin"
        assert "max-age=" in result.headers["strict-transport-security"]
        assert (
            result.headers["content-security-policy"]
            == "default-src 'none'; frame-ancestors 'none'"
        )

    async def test_applies_even_to_an_error_response(self, client: AsyncClient) -> None:
        result = await client.get("/connections")  # unauthenticated -> 401

        assert result.status_code == 401
        assert result.headers["x-frame-options"] == "DENY"

    async def test_does_not_apply_to_the_interactive_docs(self, client: AsyncClient) -> None:
        result = await client.get("/docs")

        assert "x-frame-options" not in result.headers
        assert "content-security-policy" not in result.headers
