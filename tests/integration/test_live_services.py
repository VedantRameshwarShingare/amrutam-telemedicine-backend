from __future__ import annotations

import asyncio
import os

import pytest
from app.core.database import engine
from app.core.redis import redis_client
from app.workers.celery_app import celery_app
from sqlalchemy import text

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_INTEGRATION") != "1",
        reason="live PostgreSQL, Redis, and Celery services are not enabled",
    ),
]


@pytest.mark.asyncio
async def test_live_postgres_and_redis_services() -> None:
    async with engine.connect() as connection:
        result = await connection.execute(text("SELECT 1"))
        assert result.scalar_one() == 1
    assert await redis_client.ping() is True


@pytest.mark.asyncio
async def test_live_celery_worker_is_reachable_and_registers_tasks() -> None:
    inspector = celery_app.control.inspect(timeout=5)
    ping = await asyncio.to_thread(inspector.ping)
    registered = await asyncio.to_thread(inspector.registered)

    assert ping
    assert registered
    task_names = {task for tasks in registered.values() for task in tasks}
    assert "app.workers.tasks.process_outbox" in task_names
    assert "app.workers.tasks.send_notification" in task_names
