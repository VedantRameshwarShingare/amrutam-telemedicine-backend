from __future__ import annotations

import asyncio

import pytest
from app.core.redis import cache_set_json

pytestmark = pytest.mark.concurrency


@pytest.mark.asyncio
async def test_concurrent_cache_writes_complete_without_lost_tasks(monkeypatch):
    class Redis:
        def __init__(self):
            self.values: dict[str, str] = {}

        async def set(self, key: str, value: str, *, ex: int) -> bool:
            await asyncio.sleep(0)
            self.values[key] = value
            return True

    from app.core import redis as redis_module

    redis = Redis()
    monkeypatch.setattr(redis_module, "redis_client", redis)
    results = await asyncio.gather(
        *(cache_set_json("concurrent-key", {"value": index}, ttl_seconds=60) for index in range(25))
    )

    assert all(results)
    assert "concurrent-key" in redis.values