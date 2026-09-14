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
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    # Dev-only fixed key so local encrypt/decrypt round-trips survive a
    # process restart. A separate key from secret_key on purpose - reusing
    # one key for both JWT signing and data encryption is bad practice.
    # Production must set a real ENCRYPTION_KEY (Fernet.generate_key()).
    encryption_key: str = "PkZQhLxgmytMSC4Pu32Jh6FT5i_UN5bGclRzJ9Or-Wk="

    cors_allow_origins: list[str] = ["http://localhost:3000"]

    sentry_dsn: str | None = None

    # Stripe (Phase 20). None in dev/test means "billing isn't configured" -
    # routes that need it degrade to a 503 rather than crashing (CLAUDE.md
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
