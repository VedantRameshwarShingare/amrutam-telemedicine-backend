from __future__ import annotations

from typing import Annotated

from app.core.security import get_current_active_user
from app.modules.users.models import User
from fastapi import Depends


class PermissionService:
    def __init__(self) -> None:
        pass

    async def can_access_user(self, current_user: User, target_user_id: str | None) -> bool:
        if str(current_user.role) == "ADMIN":
            return True
        return bool(target_user_id and current_user.id.hex == target_user_id)


permission_service = PermissionService()


async def get_current_user_context(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    return current_user
