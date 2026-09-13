# packages/shared (`cp_shared`)

The single SQLAlchemy `Base`/metadata shared by `apps/api`'s own tables
(users, tenants, memberships - platform concerns) and `packages/domain`'s
tables (products, orders, ... - the e-commerce domain), plus the mixins
every table composes from:

- `UUIDPrimaryKeyMixin` - UUID primary key.
- `TimestampMixin` - `created_at`/`updated_at`.
- `TenantScopedMixin` - the `tenant_id` FK every business table carries.

Installed as an editable local package (`pip install -e packages/shared`)
so `packages/domain` and `apps/api` can both depend on it without
depending on each other. See `apps/api/requirements.txt` for how it's
wired in.
