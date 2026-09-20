from __future__ import annotations

import os

if os.getenv("RUN_LIVE_INTEGRATION") != "1":
    os.environ["APP_ENV"] = "test"
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./amrutam_test.db"
    os.environ["LOGIN_RATE_LIMIT"] = "10000"
    os.environ["REGISTRATION_RATE_LIMIT"] = "10000"
    os.environ["REFRESH_RATE_LIMIT"] = "10000"
    os.environ["MFA_RATE_LIMIT"] = "10000"

import pytest
from app.core.base import Base
from app.core.database import engine
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    async def reset_db() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    import anyio

    anyio.run(reset_db)
    with TestClient(app) as test_client:
        yield test_client
