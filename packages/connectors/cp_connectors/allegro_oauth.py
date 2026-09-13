from urllib.parse import urlencode

import httpx
from pydantic import BaseModel

from cp_connectors.exceptions import ConnectorAuthError, ConnectorError

_DEFAULT_TIMEOUT_SECONDS = 15.0

# Production Allegro OAuth endpoints. Pass allegrosandbox.pl equivalents
# via auth_base_url for testing against Allegro's sandbox environment.
ALLEGRO_AUTH_BASE_URL = "https://allegro.pl/auth/oauth"


class AllegroTokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    expires_in: int
    token_type: str
    scope: str | None = None


def build_authorization_url(
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
    auth_base_url: str = ALLEGRO_AUTH_BASE_URL,
) -> str:
    """The URL to redirect the seller to for OAuth2 consent (Authorization
    Code flow - required to act on a specific Allegro seller account, as
    opposed to Client Credentials which only reaches public data).

    `state` must be a random, unguessable value generated and stored per
    pending connection attempt; the callback handling the redirect back
    must verify it matches before exchanging the code, or a CSRF attacker
    could link their own Allegro account to the victim's tenant.
    """
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return f"{auth_base_url}/authorize?{urlencode(params)}"


async def exchange_code_for_token(
    *,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    code: str,
    auth_base_url: str = ALLEGRO_AUTH_BASE_URL,
    client: httpx.AsyncClient | None = None,
) -> AllegroTokenResponse:
    """Exchanges the authorization code from the redirect callback for an
    access/refresh token pair. `code` is single-use - a retry after a
    network failure here must not resubmit the same code twice; the
    caller should treat a failed exchange as needing a fresh consent
    round-trip, not a blind retry."""
    return await _request_token(
        {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri},
        client_id=client_id,
        client_secret=client_secret,
        auth_base_url=auth_base_url,
        client=client,
    )


async def refresh_access_token(
    *,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    auth_base_url: str = ALLEGRO_AUTH_BASE_URL,
    client: httpx.AsyncClient | None = None,
) -> AllegroTokenResponse:
    """Allegro access tokens are short-lived (~12h); call this with the
    refresh_token from the last AllegroTokenResponse to get a new pair
    without the seller having to re-consent."""
    return await _request_token(
        {"grant_type": "refresh_token", "refresh_token": refresh_token},
        client_id=client_id,
        client_secret=client_secret,
        auth_base_url=auth_base_url,
        client=client,
    )


async def _request_token(
    data: dict[str, str],
    *,
    client_id: str,
    client_secret: str,
    auth_base_url: str,
    client: httpx.AsyncClient | None,
) -> AllegroTokenResponse:
    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT_SECONDS)
    try:
        response = await http_client.post(
            f"{auth_base_url}/token", data=data, auth=(client_id, client_secret)
        )
    finally:
        if owns_client:
            await http_client.aclose()

    if response.status_code in (400, 401):
        raise ConnectorAuthError(f"Allegro token request rejected: {response.text}")
    if response.status_code >= 400:
        raise ConnectorError(
            f"Allegro token request failed with {response.status_code}: {response.text}"
        )

    return AllegroTokenResponse.model_validate(response.json())
