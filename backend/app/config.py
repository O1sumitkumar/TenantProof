from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://tenantproof:tenantproof@localhost:5432/tenantproof"
    redis_url: str = "redis://localhost:6379/0"
    llm_mode: Literal["live", "fixture"] = "live"
    # M0 only: serve a fixed dev caseworker until real login lands in M1.
    # Off by default so a hosted deploy is never open; compose/.env/tests turn it on.
    dev_stub_auth: bool = False
    dev_user_email: str = "sam@example-clinic.test"
    web_dir: str = "../web"
    public_base_url: str = "http://localhost:8000"
    intake_token_ttl_days: int = 14


@lru_cache
def get_settings() -> Settings:
    return Settings()
