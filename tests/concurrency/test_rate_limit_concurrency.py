from __future__ import annotations

import asyncio

import pytest
from app.common.exceptions import RateLimitExceededError
from app.core import security
from app.core.config import settings

pytestmark = pytest.mark.concurrency


@pytest.mark.asyncio
async def test_concurrent_rate_limit_requests_are_counted_atomically(monkeypatch):
    class AtomicRedis:
        def __init__(self):
            self.count = 0
            self.lock = asyncio.Lock()

        async def incr(self, key: str) -> int:
            async with self.lock:
                self.count += 1
                return self.count

        async def expire(self, key: str, seconds: int) -> bool:
            return True

    redis = AtomicRedis()
    monkeypatch.setattr(security, "redis_client", redis)
    monkeypatch.setattr(settings, "login_rate_limit", 5)

    results = await asyncio.gather(
        *(security.rate_limit_login("concurrent@example.com", "127.0.0.1") for _ in range(20)),
        return_exceptions=True,
    )

    assert redis.count == 20
    assert sum(isinstance(result, RateLimitExceededError) for result in results) == 15