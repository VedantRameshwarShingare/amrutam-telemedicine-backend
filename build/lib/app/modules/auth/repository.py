from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.modules.users.models import User, UserRole
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email.lower())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: UUID) -> User | None:
        stmt = select(User).where(User.id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_phone(self, phone: str) -> User | None:
        stmt = select(User).where(User.phone == phone)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, *, email: str, phone: str, password_hash: str, role: UserRole) -> User:
        user = User(
            email=email.lower(),
            phone=phone,
            password_hash=password_hash,
            role=role,
            mfa_enabled=False,
            mfa_secret=None,
            is_active=True,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def update(self, user: User) -> User:
        user.updated_at = datetime.now(UTC)
        await self.session.flush()
        return user
