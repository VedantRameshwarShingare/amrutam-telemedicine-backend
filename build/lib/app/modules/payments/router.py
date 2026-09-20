from __future__ import annotations

from typing import Annotated
from uuid import UUID

from app.core.database import get_db
from app.core.security import get_current_active_user
from app.modules.payments.models import Payment
from app.modules.payments.schemas import PaymentCreateRequest, PaymentResponse
from app.modules.payments.service import PaymentService
from app.modules.users.models import User, UserRole
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/payments", tags=["Payments"])
CurrentUser = Annotated[User, Depends(get_current_active_user)]


@router.post("", response_model=PaymentResponse, status_code=201)
async def create_payment(
    payload: PaymentCreateRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Payment:
    if current_user.role != UserRole.PATIENT:
        from app.common.exceptions import AuthorizationError

        raise AuthorizationError("Only patients can create payments")
    return await PaymentService(db).create_payment(
        patient=current_user,
        booking_id=payload.booking_id,
        currency=payload.currency,
        idempotency_key=payload.idempotency_key,
    )


@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    payment_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Payment:
    return await PaymentService(db).get_payment(payment_id, current_user)
