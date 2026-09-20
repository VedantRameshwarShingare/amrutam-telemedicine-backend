from __future__ import annotations

import pytest
from app.common.exceptions import RateLimitExceededError
from app.core import redis as redis_module
from app.core import security
from app.core.config import settings
from app.modules.analytics import service as analytics_module
from app.modules.analytics.service import AnalyticsService
from app.workers.celery_app import celery_app
from app.workers.tasks import send_notification


class FakeRedis:
    def __init__(self, count: int = 0) -> None:
        self.count = count
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.count += 1
        return self.count

    async def expire(self, key: str, seconds: int) -> bool:
        self.expirations[key] = seconds
        return True

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ex: int) -> bool:
        self.values[key] = value
        self.expirations[key] = ex
        return True

    async def delete(self, *keys: str) -> int:
        for key in keys:
            self.values.pop(key, None)
        return len(keys)


@pytest.mark.asyncio
async def test_rate_limit_enforces_limit_and_preserves_window(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(security, "redis_client", fake)
    monkeypatch.setattr(settings, "login_rate_limit", 1)
    monkeypatch.setattr(settings, "login_rate_limit_seconds", 30)

    await security.rate_limit_login("person@example.com", "127.0.0.1")
    with pytest.raises(RateLimitExceededError):
        await security.rate_limit_login("person@example.com", "127.0.0.1")

    assert fake.expirations["login:person@example.com:127.0.0.1"] == 30


@pytest.mark.asyncio
async def test_rate_limit_fails_open_when_redis_is_unavailable(monkeypatch):
    class BrokenRedis:
        async def incr(self, key: str) -> int:
            raise ConnectionError("redis unavailable")

    monkeypatch.setattr(security, "redis_client", BrokenRedis())
    await security.rate_limit_login("person@example.com", "127.0.0.1")


@pytest.mark.asyncio
async def test_json_cache_round_trip_and_failure_is_fail_open(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(redis_module, "redis_client", fake)

    assert await redis_module.cache_set_json("key", {"value": 3}, ttl_seconds=60)
    assert await redis_module.cache_get_json("key") == {"value": 3}
    assert await redis_module.cache_delete("key")
    assert await redis_module.cache_get_json("key") is None


def test_notification_task_and_celery_schedules():
    result = send_notification.run("person@example.com", "Subject", "Body")

    assert result["status"] == "queued"
    assert {
        "process-outbox-every-minute",
        "send-appointment-reminders-hourly",
        "generate-daily-report",
        "refresh-analytics-cache",
    } == set(celery_app.conf.beat_schedule)


@pytest.mark.asyncio
async def test_analytics_service_uses_cached_summary(monkeypatch):
    cached = {"window_days": 30, "bookings": 2}

    async def cached_summary(key: str):
        return cached

    monkeypatch.setattr(analytics_module, "cache_get_json", cached_summary)
    result = await AnalyticsService(None).summary()

    assert result == cached