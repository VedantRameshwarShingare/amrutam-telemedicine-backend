from __future__ import annotations

import json
from typing import Any

import redis.asyncio as redis
from app.core.config import settings

redis_client = redis.from_url(
	settings.redis_url,
	decode_responses=True,
	socket_connect_timeout=0.5,
	socket_timeout=0.5,
	retry_on_timeout=False,
)


async def cache_get_json(key: str) -> dict[str, Any] | list[Any] | None:
	try:
		value = await redis_client.get(key)
		return json.loads(value) if value else None
	except Exception:
		return None


async def cache_set_json(key: str, value: object, *, ttl_seconds: int) -> bool:
	try:
		await redis_client.set(key, json.dumps(value), ex=ttl_seconds)
		return True
	except Exception:
		return False


async def cache_delete(*keys: str) -> bool:
	try:
		await redis_client.delete(*keys)
		return True
	except Exception:
		return False
