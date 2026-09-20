from __future__ import annotations

import secrets
from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "amrutam-telemedicine"
    app_env: str = "development"
    app_debug: bool = False
    app_version: str = "0.1.0"

    postgres_db: str = "amrutam"
    postgres_user: str = "amrutam"
    postgres_password: str = "amrutam_password"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    database_url: str = "sqlite+aiosqlite:///./amrutam.db"

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_url: str = "redis://localhost:6379/0"

    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    jwt_secret_key: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7
    mfa_issuer: str = "Amrutam Telemedicine"

    cors_origins: str = "http://localhost:3000,http://localhost:8000"
    log_level: str = "INFO"
    rate_limit_per_minute: int = 60
    login_rate_limit: int = 5
    registration_rate_limit: int = 3
    refresh_rate_limit: int = 10
    mfa_rate_limit: int = 5
    login_rate_limit_seconds: int = 60
    registration_rate_limit_seconds: int = 60
    refresh_rate_limit_seconds: int = 60
    mfa_rate_limit_seconds: int = 60

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_production_settings(self) -> Settings:
        if self.app_env.lower() in {"prod", "production"}:
            placeholder_markers = ("change-me", "replace", "example", "your-")
            if self.database_url.startswith("sqlite"):
                raise ValueError("Production deployments must use PostgreSQL")
            if self.postgres_password == "amrutam_password":
                raise ValueError("POSTGRES_PASSWORD must be changed in production")
            if "*" in self.cors_origins_list:
                raise ValueError("Wildcard CORS origins are not allowed in production")
            if any(not origin.lower().startswith("https://") for origin in self.cors_origins_list):
                raise ValueError("Production CORS origins must use HTTPS")
            if len(self.jwt_secret_key) < 32 or any(
                marker in self.jwt_secret_key.lower() for marker in placeholder_markers
            ):
                raise ValueError("JWT_SECRET_KEY must be a non-placeholder secret in production")
            if self.jwt_algorithm != "HS256":
                raise ValueError("Only HS256 is supported by the configured JWT implementation")
        return self

    @property
    def postgres_dsn(self) -> str:
        return self.database_url

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
