from __future__ import annotations

from typing import Annotated

from app.core.database import get_db
from app.core.security import require_role
from app.modules.analytics.service import AnalyticsService
from app.modules.users.models import User, UserRole
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/summary")
async def analytics_summary(
    _: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, object]:
    return await AnalyticsService(db).summary()