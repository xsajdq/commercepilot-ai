import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User

pytestmark = pytest.mark.asyncio(loop_scope="session")

ALICE = {
    "email": "alice-admin@example.com",
    "password": "supersecret123",
    "full_name": "Alice A",
    "tenant_name": "Alice Shop",
}
BOB = {
    "email": "bob-admin@example.com",
    "password": "supersecret123",
    "full_name": "Bob B",
    "tenant_name": "Bob Shop",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _register(client: AsyncClient, payload: dict) -> str:
    response = await client.post("/auth/register", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


async def _promote_to_platform_admin(db_session: AsyncSession, email: str) -> None:
    user = await db_session.scalar(select(User).where(User.email == email))
    user.is_platform_admin = True
    await db_session.commit()


class TestPlatformAdminGate:
    async def test_a_normal_user_is_rejected(self, client: AsyncClient) -> None:
        token = await _register(client, ALICE)
        response = await client.get("/admin/tenants", headers=_auth(token))
        assert response.status_code == 403

    async def test_unauthenticated_is_rejected(self, client: AsyncClient) -> None:
        response = await client.get("/admin/tenants")
        assert response.status_code == 401

    async def test_a_promoted_user_can_list_tenants(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token = await _register(client, ALICE)
        await _promote_to_platform_admin(db_session, ALICE["email"])

        response = await client.get("/admin/tenants", headers=_auth(token))
        assert response.status_code == 200
        names = [t["name"] for t in response.json()]
        assert "Alice Shop" in names

    async def test_me_reports_platform_admin_flag(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token = await _register(client, ALICE)
        await _promote_to_platform_admin(db_session, ALICE["email"])

        me = await client.get("/auth/me", headers=_auth(token))
        assert me.json()["user"]["is_platform_admin"] is True


class TestAdminTenantSummaries:
    async def test_summary_reflects_connections_and_member_count(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        alice_token = await _register(client, ALICE)
        await _promote_to_platform_admin(db_session, ALICE["email"])
        bob_token = await _register(client, BOB)

        await client.post(
            "/connections",
            json={"platform": "woocommerce", "name": "Bob Store", "credentials": {}},
            headers=_auth(bob_token),
        )

        response = await client.get("/admin/tenants", headers=_auth(alice_token))
        assert response.status_code == 200
        bob_summary = next(t for t in response.json() if t["name"] == "Bob Shop")
        assert bob_summary["member_count"] == 1
        assert bob_summary["connection_count"] == 1
        assert bob_summary["connection_error_count"] == 0
        assert bob_summary["plan"] == "free"

    async def test_listing_tenants_never_leaks_credentials(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        alice_token = await _register(client, ALICE)
        await _promote_to_platform_admin(db_session, ALICE["email"])
        bob_token = await _register(client, BOB)
        await client.post(
            "/connections",
            json={
                "platform": "woocommerce",
                "name": "Bob Store",
                "credentials": {"consumer_key": "ck_super_secret"},
            },
            headers=_auth(bob_token),
        )

        response = await client.get("/admin/tenants", headers=_auth(alice_token))
        assert "ck_super_secret" not in response.text


class TestAdminTenantDetail:
    async def test_detail_includes_members_and_connections(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        alice_token = await _register(client, ALICE)
        await _promote_to_platform_admin(db_session, ALICE["email"])
        bob_token = await _register(client, BOB)
        await client.post(
            "/connections",
            json={"platform": "woocommerce", "name": "Bob Store", "credentials": {}},
            headers=_auth(bob_token),
        )

        tenants = await client.get("/admin/tenants", headers=_auth(alice_token))
        bob_tenant_id = next(t for t in tenants.json() if t["name"] == "Bob Shop")["id"]

        detail = await client.get(f"/admin/tenants/{bob_tenant_id}", headers=_auth(alice_token))
        assert detail.status_code == 200
        body = detail.json()
        assert body["name"] == "Bob Shop"
        assert [m["email"] for m in body["members"]] == [BOB["email"]]
        assert [c["name"] for c in body["connections"]] == ["Bob Store"]

    async def test_unknown_tenant_404s(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token = await _register(client, ALICE)
        await _promote_to_platform_admin(db_session, ALICE["email"])

        response = await client.get(
            "/admin/tenants/00000000-0000-0000-0000-000000000000", headers=_auth(token)
        )
        assert response.status_code == 404

    async def test_a_normal_user_cannot_view_tenant_detail(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        alice_token = await _register(client, ALICE)
        bob_token = await _register(client, BOB)

        me = await client.get("/auth/me", headers=_auth(bob_token))
        bob_tenant_id = me.json()["tenant"]["id"]

        response = await client.get(
            f"/admin/tenants/{bob_tenant_id}", headers=_auth(alice_token)
        )
        assert response.status_code == 403
