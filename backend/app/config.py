from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://tenantproof:tenantproof@localhost:5432/tenantproof"
    redis_url: str = "redis://localhost:6379/0"
    llm_mode: Literal["live", "fixture"] = "live"
    # Session cookie. Secure must stay true anywhere but plain-http localhost (compose sets false).
    cookie_secure: bool = True
    session_ttl_hours: int = 12
    # Password for the seeded caseworkers. Required to seed; never committed.
    seed_password: str | None = None
    # Rate-limit counters live in Redis so they hold across API replicas (tests and CI too).
    rate_limit_storage_uri: str | None = None
    login_rate_limit: str = "10/minute"
    submit_rate_limit: str = "20/minute"
    # Content-addressed blob store (package zips now, evidence in M2).
    storage_dir: str = "./data/storage"
    web_dir: str = "../web"
    public_base_url: str = "http://localhost:8000"
    intake_token_ttl_days: int = 14


    @property
    def limiter_uri(self) -> str:
        return self.rate_limit_storage_uri or self.redis_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
