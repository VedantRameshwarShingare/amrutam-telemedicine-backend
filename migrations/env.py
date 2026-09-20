from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from app.core.base import Base
from app.core.config import settings
from app.modules.auth import models as _auth_models  # noqa: F401
from app.modules.bookings import models as _booking_models  # noqa: F401
from app.modules.consultations import models as _consultation_models  # noqa: F401
from app.modules.doctors import models as _doctor_models  # noqa: F401
from app.modules.payments import models as _payment_models  # noqa: F401
from app.modules.prescriptions import models as _prescription_models  # noqa: F401
from app.modules.users import models as _user_models  # noqa: F401
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async def run_async() -> None:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)

    asyncio.run(run_async())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
