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

    cors_allow_origins: list[str] = ["http://localhost:3000"]

    sentry_dsn: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
