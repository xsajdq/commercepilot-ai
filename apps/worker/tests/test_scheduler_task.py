from decimal import Decimal

from tests.conftest import make_connection, make_offer_with_price, make_product, make_tenant
from worker.tasks.scheduler import dispatch_daily_recommendations, dispatch_daily_sync


class TestDispatchDailySync:
    def test_enqueues_a_sync_for_every_connection(self, monkeypatch) -> None:
        calls = []
        monkeypatch.setattr(
            "worker.tasks.scheduler.sync_connection.delay",
            lambda tenant_id, connection_id: calls.append((tenant_id, connection_id)),
        )
        tenant_id = make_tenant()
        connection_id = make_connection(tenant_id, {"access_token": "tok"})

        result = dispatch_daily_sync.run()

        assert result == {"connections_synced": 1}
        assert calls == [(str(tenant_id), str(connection_id))]

    def test_no_connections_dispatches_nothing(self, monkeypatch) -> None:
        calls = []
        monkeypatch.setattr(
            "worker.tasks.scheduler.sync_connection.delay",
            lambda *args: calls.append(args),
        )

        result = dispatch_daily_sync.run()

        assert result == {"connections_synced": 0}
        assert calls == []

    def test_enqueues_one_sync_per_connection_across_tenants(self, monkeypatch) -> None:
        calls = []
        monkeypatch.setattr(
            "worker.tasks.scheduler.sync_connection.delay",
            lambda tenant_id, connection_id: calls.append((tenant_id, connection_id)),
        )
        tenant_a = make_tenant("Tenant A")
        tenant_b = make_tenant("Tenant B")
        make_connection(tenant_a, {"access_token": "tok-a"})
        make_connection(tenant_b, {"access_token": "tok-b"})

        result = dispatch_daily_sync.run()

        assert result == {"connections_synced": 2}
        assert len(calls) == 2


class TestDispatchDailyRecommendations:
    def _patch_all(self, monkeypatch):
        calls = {"catalog": [], "analytics": [], "pricing": [], "listing": []}
        monkeypatch.setattr(
            "worker.tasks.scheduler.run_catalog_audit.delay",
            lambda tenant_id: calls["catalog"].append(tenant_id),
        )
        monkeypatch.setattr(
            "worker.tasks.scheduler.generate_dashboard_narrative.delay",
            lambda tenant_id: calls["analytics"].append(tenant_id),
        )
        monkeypatch.setattr(
            "worker.tasks.scheduler.generate_price_recommendation.delay",
            lambda tenant_id, offer_id: calls["pricing"].append((tenant_id, offer_id)),
        )
        monkeypatch.setattr(
            "worker.tasks.scheduler.generate_listing_publish_recommendation.delay",
            lambda tenant_id, offer_id: calls["listing"].append((tenant_id, offer_id)),
        )
        return calls

    def test_dispatches_catalog_and_analytics_for_a_tenant_with_products(
        self, monkeypatch
    ) -> None:
        calls = self._patch_all(monkeypatch)
        tenant_id = make_tenant()
        make_product(tenant_id, sku="SKU-1")

        result = dispatch_daily_recommendations.run()

        assert calls["catalog"] == [str(tenant_id)]
        assert calls["analytics"] == [str(tenant_id)]
        assert result["tenants_processed"] == 1

    def test_skips_a_tenant_with_no_products(self, monkeypatch) -> None:
        calls = self._patch_all(monkeypatch)
        make_tenant()

        result = dispatch_daily_recommendations.run()

        assert calls["catalog"] == []
        assert calls["analytics"] == []
        assert result["tenants_processed"] == 0

    def test_dispatches_pricing_for_every_priced_offer(self, monkeypatch) -> None:
        calls = self._patch_all(monkeypatch)
        tenant_id = make_tenant()
        connection_id = make_connection(tenant_id, {"access_token": "tok"})
        offer_id = make_offer_with_price(
            tenant_id, connection_id, price_amount=Decimal("100.00")
        )

        result = dispatch_daily_recommendations.run()

        assert calls["pricing"] == [(str(tenant_id), str(offer_id))]
        assert result["pricing_checks_queued"] == 1

    def test_does_not_dispatch_pricing_for_an_unpriced_offer(self, monkeypatch) -> None:
        calls = self._patch_all(monkeypatch)
        tenant_id = make_tenant()
        connection_id = make_connection(tenant_id, {"access_token": "tok"})
        make_offer_with_price(tenant_id, connection_id, price_amount=None)

        result = dispatch_daily_recommendations.run()

        assert calls["pricing"] == []
        assert result["pricing_checks_queued"] == 0

    def test_dispatches_listing_check_only_for_offers_with_an_external_id(
        self, monkeypatch
    ) -> None:
        calls = self._patch_all(monkeypatch)
        tenant_id = make_tenant()
        connection_id = make_connection(tenant_id, {"access_token": "tok"})
        listed_offer_id = make_offer_with_price(
            tenant_id, connection_id, sku="A", external_id="ext-1"
        )
        make_offer_with_price(tenant_id, connection_id, sku="B", external_id=None)

        result = dispatch_daily_recommendations.run()

        assert calls["listing"] == [(str(tenant_id), str(listed_offer_id))]
        assert result["listing_checks_queued"] == 1

    def test_never_dispatches_content_generation(self, monkeypatch) -> None:
        """Phase 15's deliberate exclusion: one real LLM call per
        product, unbounded across a whole catalog, with no cost guard
        until Phase 20 - this proves the scheduler module doesn't even
        reference that task."""
        import worker.tasks.scheduler as scheduler_module

        assert not hasattr(scheduler_module, "generate_product_content_recommendation")
