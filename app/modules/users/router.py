from __future__ import annotations

from typing import Annotated
from uuid import UUID

from app.common.exceptions import ResourceNotFoundError
from app.core.database import get_db
from app.core.security import get_current_active_user
from app.modules.auth.schemas import UserPublicResponse
from app.modules.users.models import User
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserPublicResponse)
async def get_current_user_profile(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    return current_user


@router.get("/{user_id}", response_model=UserPublicResponse)
async def get_user_by_id(
    user_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if current_user.id != user_id and str(current_user.role) != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {
                    "code": "FORBIDDEN",
                    "message": "Not allowed to access another user",
                }
            },
        )

    user = await db.get(User, user_id)
    if user is None:
        raise ResourceNotFoundError("User not found")
    return user
