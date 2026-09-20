from __future__ import annotations

from typing import Annotated
from uuid import UUID

from app.core.database import get_db
from app.core.security import get_current_active_user
from app.modules.consultations.models import Consultation
from app.modules.consultations.schemas import (
    ConsultationCreateRequest,
    ConsultationResponse,
    ConsultationStatusRequest,
)
from app.modules.consultations.service import ConsultationService
from app.modules.users.models import User
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/consultations", tags=["Consultations"])
CurrentUser = Annotated[User, Depends(get_current_active_user)]


@router.post("", response_model=ConsultationResponse, status_code=201)
async def create_consultation(
    payload: ConsultationCreateRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Consultation:
    consultation = await ConsultationService(db).create(
        actor=current_user,
        booking_id=payload.booking_id,
        idempotency_key=payload.idempotency_key,
        clinical_notes=payload.clinical_notes,
    )
    await db.commit()
    return consultation


@router.get("/{consultation_id}", response_model=ConsultationResponse)
async def get_consultation(
    consultation_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Consultation:
    service = ConsultationService(db)
    consultation = await service.get(consultation_id)
    await service.authorize_read(consultation, current_user)
    return consultation


@router.patch("/{consultation_id}/status", response_model=ConsultationResponse)
async def update_consultation_status(
    consultation_id: UUID,
    payload: ConsultationStatusRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Consultation:
    consultation = await ConsultationService(db).update_status(
        consultation_id=consultation_id,
        actor=current_user,
        status=payload.status,
        clinical_notes=payload.clinical_notes,
    )
    await db.commit()
    return consultation
