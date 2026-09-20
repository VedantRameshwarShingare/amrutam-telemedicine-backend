from __future__ import annotations

from typing import Annotated
from uuid import UUID

from app.core.database import get_db
from app.core.security import get_current_active_user
from app.modules.prescriptions.models import Prescription
from app.modules.prescriptions.schemas import PrescriptionCreateRequest, PrescriptionResponse
from app.modules.prescriptions.service import PrescriptionService
from app.modules.users.models import User
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/prescriptions", tags=["Prescriptions"])
CurrentUser = Annotated[User, Depends(get_current_active_user)]


@router.post(
    "/consultations/{consultation_id}",
    response_model=PrescriptionResponse,
    status_code=201,
)
async def create_prescription(
    consultation_id: UUID,
    payload: PrescriptionCreateRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Prescription:
    prescription = await PrescriptionService(db).create(
        consultation_id=consultation_id,
        actor=current_user,
        idempotency_key=payload.idempotency_key,
        medications=[item.model_dump() for item in payload.medications],
        instructions=payload.instructions,
    )
    await db.commit()
    return prescription


@router.get("/{prescription_id}", response_model=PrescriptionResponse)
async def get_prescription(
    prescription_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Prescription:
    return await PrescriptionService(db).get(prescription_id, current_user)
