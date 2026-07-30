from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    # Own dedicated database - must never point at the ShadowAI product DB.
    database_url: str = (
        "postgresql+psycopg://residency:residency@localhost:5433/residency_tracker"
    )
    dashboard_origins: list[str] = ["http://localhost:5174"]

    # Single-operator auth: one shared secret for the human (frontend). No
    # user accounts/RBAC - there is exactly one operator. Must be overridden
    # in production; the empty-string default only exists so local
    # `alembic`/pytest invocations don't require an .env.
    admin_token: str = ""

    # How often the scheduler loop checks for due sources.
    scheduler_interval_seconds: int = 900


@lru_cache
def get_settings() -> Settings:
    return Settings()
