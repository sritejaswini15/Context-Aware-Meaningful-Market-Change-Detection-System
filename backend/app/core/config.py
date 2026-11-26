"""Application configuration.

All configuration comes from environment variables (or a local `.env` file in
development). In AWS, ECS injects secrets from Secrets Manager as environment
variables, so the application never talks to Secrets Manager directly.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-insecure-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    app_version: str = "1.0.0"
    api_prefix: str = "/api"
    log_level: str = "INFO"
    log_json: bool = True

    database_url: str = "postgresql+psycopg://knoww:knoww@localhost:5432/knoww"
    database_pool_size: int = 5
    redis_url: str | None = None

    cors_origins: str = "http://localhost:3000"

    # --- Authentication -------------------------------------------------
    auth_mode: Literal["local", "cognito"] = "local"
    jwt_secret: str = DEV_JWT_SECRET
    jwt_ttl_minutes: int = 60 * 24 * 7
    cookie_secure: bool = False
    cookie_domain: str | None = None
    cognito_region: str | None = None
    cognito_user_pool_id: str | None = None
    cognito_client_id: str | None = None

    # --- Market data ----------------------------------------------------
    # Comma-separated, in priority order. Options: mock, mock-reference, finnhub
    market_providers: str = "mock,mock-reference"
    finnhub_api_key: str | None = None
    provider_timeout_seconds: float = 6.0
    provider_max_retries: int = 2
    quote_cache_ttl_seconds: int = 15
    conflict_tolerance_pct: float = 1.0
    market_refresh_seconds: int = 60
    benchmark_symbol: str = "SPY"

    # --- AI explanation layer -------------------------------------------
    ai_provider: Literal["anthropic", "openai", "none"] = "none"
    ai_api_key: str | None = None
    ai_model: str | None = None
    ai_base_url: str | None = None
    ai_timeout_seconds: float = 15.0

    # --- Async processing -----------------------------------------------
    queue_backend: Literal["inline", "sqs"] = "inline"
    sqs_queue_url: str | None = None
    aws_region: str = "ap-south-1"
    aws_endpoint_url: str | None = None  # e.g. ElasticMQ locally
    scheduler_mode: Literal["local", "eventbridge", "off"] = "local"

    # --- Product --------------------------------------------------------
    demo_mode: bool = True
    active_user_days: int = 30

    sentry_dsn: str | None = None

    @model_validator(mode="after")
    def _production_guards(self) -> "Settings":
        if self.app_env == "production":
            if self.auth_mode == "local" and self.jwt_secret == DEV_JWT_SECRET:
                raise ValueError("JWT_SECRET must be set in production")
            if self.auth_mode == "cognito" and not (self.cognito_user_pool_id and self.cognito_client_id):
                raise ValueError("Cognito configuration is required when AUTH_MODE=cognito")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def market_provider_list(self) -> list[str]:
        return [p.strip() for p in self.market_providers.split(",") if p.strip()]

    @property
    def uses_mock_market(self) -> bool:
        return any(p.startswith("mock") for p in self.market_provider_list)


@lru_cache
def get_settings() -> Settings:
    return Settings()
