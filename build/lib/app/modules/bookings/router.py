from __future__ import annotations

from typing import Annotated
from uuid import UUID

from app.common.exceptions import AuthorizationError, ResourceNotFoundError
from app.core.database import get_db
from app.core.security import get_current_active_user
from app.modules.bookings.models import Booking
from app.modules.bookings.schemas import (
    BookingCancelRequest,
    BookingCreateRequest,
    BookingListResponse,
    BookingResponse,
)
from app.modules.bookings.service import BookingService
from app.modules.doctors.models import Doctor
from app.modules.users.models import User, UserRole
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/bookings", tags=["Bookings"])
CurrentUser = Annotated[User, Depends(get_current_active_user)]


@router.post("", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
async def create_booking(
    payload: BookingCreateRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Booking:
    if current_user.role != UserRole.PATIENT:
        raise AuthorizationError("Only patients can create bookings")
    service = BookingService(db)
    booking = await service.create_booking(
        patient=current_user,
        slot_id=payload.slot_id,
        idempotency_key=payload.idempotency_key,
    )
    await db.commit()
    return booking


@router.get("", response_model=BookingListResponse)
async def list_bookings(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> BookingListResponse:
    service = BookingService(db)
    patient_id: UUID | None = current_user.id if current_user.role == UserRole.PATIENT else None
    doctor_id: UUID | None = None
    if current_user.role == UserRole.DOCTOR:
        doctor = await db.scalar(select(Doctor).where(Doctor.user_id == current_user.id))
        doctor_id = doctor.id if doctor else UUID(int=0)
    if current_user.role not in {UserRole.PATIENT, UserRole.DOCTOR, UserRole.ADMIN}:
        raise AuthorizationError("You are not authorized to list bookings")
    items, total = await service.repository.list_for_user(
        patient_id=patient_id,
        doctor_id=doctor_id,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return BookingListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{booking_id}", response_model=BookingResponse)
async def get_booking(
    booking_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Booking:
    service = BookingService(db)
    booking = await service.repository.get_by_id(booking_id)
    if booking is None:
        raise ResourceNotFoundError("Booking not found")
    doctor = await db.get(Doctor, booking.doctor_id)
    allowed = current_user.role == UserRole.ADMIN or booking.patient_id == current_user.id
    allowed = allowed or bool(doctor and doctor.user_id == current_user.id)
    if not allowed:
        raise AuthorizationError("You are not authorized to access this booking")
    return booking


@router.post("/{booking_id}/cancel", response_model=BookingResponse)
async def cancel_booking(
    booking_id: UUID,
    payload: BookingCancelRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Booking:
    booking = await BookingService(db).cancel_booking(
        booking_id=booking_id,
        actor=current_user,
        reason=payload.reason,
    )
    await db.commit()
    return booking
