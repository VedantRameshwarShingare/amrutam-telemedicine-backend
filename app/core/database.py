from __future__ import annotations

from collections.abc import AsyncGenerator

from app.core.config import settings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

engine_kwargs: dict[str, object] = {"pool_pre_ping": True, "echo": settings.app_debug}
if settings.database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_async_engine(settings.postgres_dsn, **engine_kwargs)
AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
