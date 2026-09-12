import uuid

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.core.config import get_settings
from app.db.models.membership import Membership, MembershipRole
from app.db.models.tenant import Tenant

# One event loop for the whole module, matching the session-scoped engine
# and schema fixtures in conftest.py - asyncpg connections are loop-bound,
# so tests and fixtures must agree on which loop they run in.
pytestmark = pytest.mark.asyncio(loop_scope="session")

ALICE = {
    "email": "alice@example.com",
    "password": "supersecret123",
    "full_name": "Alice A",
    "tenant_name": "Alice Shop",
}
BOB = {
    "email": "bob@example.com",
    "password": "supersecret123",
    "full_name": "Bob B",
    "tenant_name": "Bob Shop",
}


async def _register(client: AsyncClient, payload: dict) -> dict:
    response = await client.post("/auth/register", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _decode(access_token: str) -> dict:
    settings = get_settings()
    return jwt.decode(access_token, settings.secret_key, algorithms=[settings.jwt_algorithm])


def _user_id_from_token(access_token: str) -> uuid.UUID:
    return uuid.UUID(_decode(access_token)["sub"])


async def _add_membership_to_new_tenant(
    db_session: AsyncSession, *, user_id: uuid.UUID, tenant_name: str
) -> dict:
    """Simulates a future 'invite an existing user to another tenant'
    feature (not yet built - Phase 1 only covers register/login/roles).
    Used here purely to set up a genuine multi-tenant user for tests."""
    tenant = Tenant(name=tenant_name, slug=tenant_name.lower().replace(" ", "-"))
    db_session.add(tenant)
    await db_session.flush()
    db_session.add(
        Membership(user_id=user_id, tenant_id=tenant.id, role=MembershipRole.OWNER)
    )
    await db_session.commit()
    return {"id": str(tenant.id), "name": tenant.name, "slug": tenant.slug}


class TestRegister:
    async def test_register_creates_owner_membership(self, client: AsyncClient) -> None:
        body = await _register(client, ALICE)
        assert body["role"] == "owner"
        assert "access_token" in body
        assert "refresh_token" in body

    async def test_register_duplicate_email_conflicts(self, client: AsyncClient) -> None:
        await _register(client, ALICE)
        response = await client.post(
            "/auth/register",
            json={**ALICE, "tenant_name": "A Different Shop"},
        )
        assert response.status_code == 409

    async def test_password_is_never_returned(self, client: AsyncClient) -> None:
        body = await _register(client, ALICE)
        assert "password" not in body
        assert "hashed_password" not in body


class TestLogin:
    async def test_login_with_single_tenant_auto_selects_it(self, client: AsyncClient) -> None:
        registered = await _register(client, ALICE)
        response = await client.post(
            "/auth/login", json={"email": ALICE["email"], "password": ALICE["password"]}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["requires_tenant_selection"] is False
        assert body["token"]["tenant_id"] == registered["tenant_id"]

    async def test_login_wrong_password_rejected(self, client: AsyncClient) -> None:
        await _register(client, ALICE)
        response = await client.post(
            "/auth/login", json={"email": ALICE["email"], "password": "wrong-password"}
        )
        assert response.status_code == 401

    async def test_login_unknown_email_rejected(self, client: AsyncClient) -> None:
        response = await client.post(
            "/auth/login", json={"email": "nobody@example.com", "password": "whatever123"}
        )
        assert response.status_code == 401

    async def test_login_multiple_tenants_requires_selection(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        registered = await _register(client, ALICE)
        second_tenant = await _add_membership_to_new_tenant(
            db_session,
            user_id=_user_id_from_token(registered["access_token"]),
            tenant_name="Alice's Second Shop",
        )

        response = await client.post(
            "/auth/login", json={"email": ALICE["email"], "password": ALICE["password"]}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["requires_tenant_selection"] is True
        tenant_ids = {m["tenant"]["id"] for m in body["memberships"]}
        assert second_tenant["id"] in tenant_ids

        response = await client.post(
            "/auth/login",
            json={
                "email": ALICE["email"],
                "password": ALICE["password"],
                "tenant_id": second_tenant["id"],
            },
        )
        assert response.status_code == 200
        assert response.json()["token"]["tenant_id"] == second_tenant["id"]


class TestRefresh:
    async def test_refresh_issues_new_working_token(self, client: AsyncClient) -> None:
        registered = await _register(client, ALICE)
        response = await client.post(
            "/auth/refresh", json={"refresh_token": registered["refresh_token"]}
        )
        assert response.status_code == 200
        new_access = response.json()["access_token"]

        me = await client.get("/auth/me", headers={"Authorization": f"Bearer {new_access}"})
        assert me.status_code == 200

    async def test_refresh_token_is_single_use(self, client: AsyncClient) -> None:
        registered = await _register(client, ALICE)
        first = await client.post(
            "/auth/refresh", json={"refresh_token": registered["refresh_token"]}
        )
        assert first.status_code == 200

        reuse = await client.post(
            "/auth/refresh", json={"refresh_token": registered["refresh_token"]}
        )
        assert reuse.status_code == 401

    async def test_garbage_refresh_token_rejected(self, client: AsyncClient) -> None:
        response = await client.post("/auth/refresh", json={"refresh_token": "not-a-real-token"})
        assert response.status_code == 401


class TestMe:
    async def test_me_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.get("/auth/me")
        assert response.status_code == 401

    async def test_me_rejects_garbage_token(self, client: AsyncClient) -> None:
        response = await client.get(
            "/auth/me", headers={"Authorization": "Bearer not-a-real-jwt"}
        )
        assert response.status_code == 401

    async def test_me_returns_own_identity(self, client: AsyncClient) -> None:
        registered = await _register(client, ALICE)
        response = await client.get(
            "/auth/me", headers={"Authorization": f"Bearer {registered['access_token']}"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["user"]["email"] == ALICE["email"]
        assert body["tenant"]["id"] == registered["tenant_id"]


class TestTenantIsolation:
    """The mandatory Phase 1 gate: a user in Tenant A must never be able to
    read or act on Tenant B's data, under any of the ways tenant_id could
    reach the backend."""

    async def test_user_cannot_switch_into_a_tenant_they_do_not_belong_to(
        self, client: AsyncClient
    ) -> None:
        alice = await _register(client, ALICE)
        bob = await _register(client, BOB)

        response = await client.post(
            "/auth/switch-tenant",
            json={"tenant_id": bob["tenant_id"]},
            headers={"Authorization": f"Bearer {alice['access_token']}"},
        )
        assert response.status_code == 403

        # Alice's own session must be completely unaffected by the attempt.
        me = await client.get(
            "/auth/me", headers={"Authorization": f"Bearer {alice['access_token']}"}
        )
        assert me.status_code == 200
        assert me.json()["tenant"]["id"] == alice["tenant_id"]

    async def test_forged_tenant_claim_is_rejected_even_with_a_validly_signed_token(
        self, client: AsyncClient
    ) -> None:
        """Defense in depth: even if a token's tenant_id claim is tampered
        with (e.g. a signing-key compromise or a future bug that lets a
        client influence claims), the membership table - not the token
        alone - is what the server trusts on every request."""
        alice = await _register(client, ALICE)
        bob = await _register(client, BOB)

        settings = get_settings()
        payload = _decode(alice["access_token"])
        payload["tenant_id"] = bob["tenant_id"]
        forged = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)

        response = await client.get("/auth/me", headers={"Authorization": f"Bearer {forged}"})
        assert response.status_code == 403

    async def test_switching_to_owned_second_tenant_succeeds(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        registered = await _register(client, ALICE)
        second = await _add_membership_to_new_tenant(
            db_session,
            user_id=_user_id_from_token(registered["access_token"]),
            tenant_name="Alice's Second Shop",
        )

        response = await client.post(
            "/auth/switch-tenant",
            json={"tenant_id": second["id"]},
            headers={"Authorization": f"Bearer {registered['access_token']}"},
        )
        assert response.status_code == 200
        assert response.json()["tenant_id"] == second["id"]


class TestRequireRole:
    def _membership(self, role: MembershipRole) -> Membership:
        return Membership(role=role)

    async def test_allows_matching_role(self) -> None:
        checker = require_role(MembershipRole.OWNER, MembershipRole.MANAGER)
        membership = self._membership(MembershipRole.MANAGER)
        assert await checker(membership) is membership

    async def test_rejects_insufficient_role(self) -> None:
        checker = require_role(MembershipRole.OWNER)
        with pytest.raises(HTTPException) as exc_info:
            await checker(self._membership(MembershipRole.VIEWER))
        assert exc_info.value.status_code == 403
