from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven configuration.

    No secrets have defaults here beyond values that are safe for local
    development; production values must come from the environment.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    api_port: int = 8000

    database_url: str = "postgresql+asyncpg://commercepilot:commercepilot@postgres:5432/commercepilot"
    redis_url: str = "redis://redis:6379/0"

    secret_key: str = "change-me-in-production"
    # Set only during a JWT signing-key rotation (Phase 21) - a still-
    # valid access token signed under the OLD key keeps verifying until
    # it naturally expires, so rotating `secret_key` never forces every
    # logged-in user to re-login mid-rotation. Remove once every token
    # issued under the old key has expired (`access_token_expire_minutes`
    # after the rotation). New tokens are always signed with `secret_key`
    # alone - this is verification-only.
    secret_key_previous: str | None = None
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    # Dev-only fixed key so local encrypt/decrypt round-trips survive a
    # process restart. A separate key from secret_key on purpose - reusing
    # one key for both JWT signing and data encryption is bad practice.
    # Production must set a real ENCRYPTION_KEY (Fernet.generate_key()).
    encryption_key: str = "PkZQhLxgmytMSC4Pu32Jh6FT5i_UN5bGclRzJ9Or-Wk="
    # Set only during an encryption-key rotation (Phase 21) - existing
    # `Connection.encrypted_credentials` rows written under the OLD key
    # still decrypt (`cp_shared.crypto` tries every key in the list) while
    # new/updated rows always encrypt under `encryption_key` alone. Run
    # `worker.reencrypt_all_connections` to migrate every row onto the
    # new key, then remove this - see docs/security/secret-rotation.md.
    encryption_key_previous: str | None = None

    cors_allow_origins: list[str] = ["http://localhost:3000"]

    sentry_dsn: str | None = None

    # Stripe (Phase 20). None in dev/test means "billing isn't configured" -
    # routes that need it degrade to a 503 rather than crashing (CONTRIBUTING.md
    # #9's "never guess" spirit applies to config too: we don't invent a
    # fake key that would silently fail against the real Stripe API).
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    # Stripe Price ids for the two paid plans - set per-environment since
    # they differ between Stripe test mode and live mode.
    stripe_price_id_starter: str | None = None
    stripe_price_id_pro: str | None = None
    # Where Stripe Checkout/Billing Portal send the browser back to.
    billing_return_url: str = "http://localhost:3000/billing"

    # Rate limiting (Phase 21) - per-IP, fixed 60s window, enforced by
    # `app/core/rate_limit.py`. Auth endpoints get a much tighter limit
    # than the rest of the API since they're the obvious brute-force
    # target (login/register/refresh). These are starting points, not
    # calibrated against real traffic yet - same caveat as
    # docs/architecture/deployment.md's alert thresholds.
    rate_limit_default_per_minute: int = 120
    rate_limit_auth_per_minute: int = 10

    @property
    def encryption_keys(self) -> list[str]:
        """Current key first (used for every new encryption), previous
        key appended only during a rotation window - see
        `encryption_key_previous`'s own docstring."""
        keys = [self.encryption_key]
        if self.encryption_key_previous:
            keys.append(self.encryption_key_previous)
        return keys

    @property
    def jwt_verification_keys(self) -> list[str]:
        """Same shape as `encryption_keys`, for JWT signature
        verification - see `secret_key_previous`'s own docstring."""
        keys = [self.secret_key]
        if self.secret_key_previous:
            keys.append(self.secret_key_previous)
        return keys


@lru_cache
def get_settings() -> Settings:
    return Settings()
