# packages/connectors

The `CommerceConnector` interface and its per-platform implementations
(`base/`, `woocommerce/`, `allegro/`, `shoper/`, `prestashop/`, `idosell/`).

Empty scaffold — the base interface and a mock connector land in Phase 3,
ahead of any real platform (WooCommerce in Phase 4, Allegro in Phase 5).
Agents must never know which platform they're talking to; they only see
this interface.
