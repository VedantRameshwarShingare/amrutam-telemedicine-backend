from __future__ import annotations

import pytest
from app.common.exceptions import RateLimitExceededError
from app.core import security
from app.core.config import Settings
from app.core.logging import redact_sensitive

pytestmark = pytest.mark.security


def test_sensitive_healthcare_and_auth_fields_are_not_loggable():
    fields = {
        "email": "patient@example.com",
        "authorization": "Bearer token",
        "clinical_notes": "diagnosis",
        "password": "secret",
        "event": "request",
    }

    redacted = redact_sensitive(None, "", fields)

    assert redacted == {"event": "request"}


@pytest.mark.asyncio
async def test_rate_limit_rejects_after_configured_threshold(monkeypatch):
    class Redis:
        def __init__(self):
            self.count = 0

        async def incr(self, key: str) -> int:
            self.count += 1
            return self.count

        async def expire(self, key: str, seconds: int) -> bool:
            return True

    redis = Redis()
    monkeypatch.setattr(security, "redis_client", redis)
    from app.core.config import settings

    monkeypatch.setattr(settings, "login_rate_limit", 1)
    await security.rate_limit_login("security@example.com", "127.0.0.1")
    with pytest.raises(RateLimitExceededError):
        await security.rate_limit_login("security@example.com", "127.0.0.1")


def test_production_settings_reject_insecure_database_defaults():
    with pytest.raises(ValueError, match="PostgreSQL"):
        Settings(
            _env_file=None,
            app_env="production",
            database_url="sqlite+aiosqlite:///./test.db",
            jwt_secret_key="x" * 32,
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"jwt_secret_key": "replace-with-a-real-secret-that-is-long-enough"},
        {"cors_origins": "http://telemedicine.example.com"},
        {"jwt_algorithm": "HS384"},
    ],
)
def test_production_settings_reject_unsafe_security_configuration(overrides):
    values = {
        "_env_file": None,
        "app_env": "production",
        "database_url": "postgresql+asyncpg://user:password@postgres:5432/db",
        "postgres_password": "real-production-password",
        "jwt_secret_key": "x" * 32,
        "cors_origins": "https://telemedicine.example.com",
    }
    values.update(overrides)
    with pytest.raises(ValueError):
        Settings(**values)