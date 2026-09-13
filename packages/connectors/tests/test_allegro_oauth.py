import httpx
import pytest

from cp_connectors.allegro_oauth import (
    AllegroTokenResponse,
    build_authorization_url,
    exchange_code_for_token,
    refresh_access_token,
)
from cp_connectors.exceptions import ConnectorAuthError, ConnectorError


def test_build_authorization_url_includes_required_params() -> None:
    url = build_authorization_url(
        client_id="client-123", redirect_uri="https://app.example.com/callback", state="xyz"
    )
    assert url.startswith("https://allegro.pl/auth/oauth/authorize?")
    assert "client_id=client-123" in url
    assert "response_type=code" in url
    assert "redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback" in url
    assert "state=xyz" in url


def _token_handler(request: httpx.Request) -> httpx.Response:
    if not request.headers.get("authorization", "").startswith("Basic "):
        return httpx.Response(401, json={"error": "invalid_client"})

    body = dict(pair.split("=") for pair in request.content.decode().split("&"))
    if body.get("grant_type") == "authorization_code" and body.get("code") == "good-code":
        return httpx.Response(
            200,
            json={
                "access_token": "access-1",
                "refresh_token": "refresh-1",
                "expires_in": 43200,
                "token_type": "bearer",
                "scope": "allegro:api:sale:offers:read",
            },
        )
    if body.get("grant_type") == "refresh_token" and body.get("refresh_token") == "refresh-1":
        return httpx.Response(
            200,
            json={
                "access_token": "access-2",
                "refresh_token": "refresh-2",
                "expires_in": 43200,
                "token_type": "bearer",
            },
        )
    return httpx.Response(400, json={"error": "invalid_grant"})


@pytest.fixture
def token_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(_token_handler))


async def test_exchange_code_for_token(token_client: httpx.AsyncClient) -> None:
    token = await exchange_code_for_token(
        client_id="client-123",
        client_secret="secret",
        redirect_uri="https://app.example.com/callback",
        code="good-code",
        client=token_client,
    )
    assert isinstance(token, AllegroTokenResponse)
    assert token.access_token == "access-1"
    assert token.refresh_token == "refresh-1"


async def test_exchange_invalid_code_raises_error(token_client: httpx.AsyncClient) -> None:
    with pytest.raises(ConnectorError):
        await exchange_code_for_token(
            client_id="client-123",
            client_secret="secret",
            redirect_uri="https://app.example.com/callback",
            code="bad-code",
            client=token_client,
        )


async def test_refresh_access_token(token_client: httpx.AsyncClient) -> None:
    token = await refresh_access_token(
        client_id="client-123",
        client_secret="secret",
        refresh_token="refresh-1",
        client=token_client,
    )
    assert token.access_token == "access-2"
    assert token.refresh_token == "refresh-2"


def _unauthorized_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(401, json={"error": "invalid_client"})


async def test_wrong_client_credentials_raise_auth_error() -> None:
    client = httpx.AsyncClient(transport=httpx.MockTransport(_unauthorized_handler))
    with pytest.raises(ConnectorAuthError):
        await exchange_code_for_token(
            client_id="wrong",
            client_secret="wrong",
            redirect_uri="https://app.example.com/callback",
            code="good-code",
            client=client,
        )
