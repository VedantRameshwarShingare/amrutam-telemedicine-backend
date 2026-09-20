from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from app.core.database import get_db
from app.core.security import get_current_active_user, require_role
from app.modules.doctors.models import AvailabilitySlot, Doctor
from app.modules.doctors.schemas import (
    AvailabilitySlotCreateRequest,
    AvailabilitySlotResponse,
    AvailabilitySlotUpdateRequest,
    DoctorCreateRequest,
    DoctorListResponse,
    DoctorResponse,
    DoctorUpdateRequest,
)
from app.modules.doctors.service import DoctorService
from app.modules.users.models import User, UserRole
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/doctors", tags=["Doctors"])

CurrentUser = Annotated[User, Depends(get_current_active_user)]
AdminUser = Annotated[User, Depends(require_role(UserRole.ADMIN))]


@router.get("", response_model=DoctorListResponse)
async def list_doctors(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    specialization: str | None = None,
    experience_min: int | None = Query(default=None, ge=0),
    availability_start: datetime | None = None,
    availability_end: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: str = Query(
        default="created_at",
        pattern="^(created_at|experience_years|consultation_fee|specialization)$",
    ),
    sort_order: str = Query(default="asc", pattern="^(asc|desc)$"),
) -> DoctorListResponse:
    if availability_start and availability_end and availability_start >= availability_end:
        from app.common.exceptions import ValidationError

        raise ValidationError("availability_start must be before availability_end")
    service = DoctorService(db)
    doctors, total = await service.list_doctors(
        specialization=specialization,
        experience_min=experience_min,
        availability_start=availability_start,
        availability_end=availability_end,
        offset=(page - 1) * page_size,
        limit=page_size,
        sort_by=sort_by,
        sort_desc=sort_order == "desc",
    )
    return DoctorListResponse(items=doctors, total=total, page=page, page_size=page_size)


@router.get("/{doctor_id}/availability", response_model=list[AvailabilitySlotResponse])
async def get_doctor_availability(
    doctor_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[AvailabilitySlot]:
    service = DoctorService(db)
    await service.get_doctor(doctor_id)
    return await service.list_availability(doctor_id, start=start, end=end)


@router.get("/{doctor_id}", response_model=DoctorResponse)
async def get_doctor(
    doctor_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Doctor:
    service = DoctorService(db)
    cached = await service.get_cached_doctor(doctor_id)
    if cached is not None:
        return cached  # type: ignore[return-value]
    doctor = await service.get_doctor(doctor_id)
    await service.cache_doctor(doctor)
    return doctor


@router.post("", response_model=DoctorResponse, status_code=status.HTTP_201_CREATED)
async def create_doctor(
    payload: DoctorCreateRequest,
    admin_user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Doctor:
    user = await db.get(User, payload.user_id)
    service = DoctorService(db)
    doctor = await service.create_doctor(
        user=user,
        user_id=payload.user_id,
        license_number=payload.license_number,
        specialization=payload.specialization,
        experience_years=payload.experience_years,
        consultation_fee=payload.consultation_fee,
        status=payload.status,
    )
    await db.commit()
    return doctor


@router.patch("/{doctor_id}", response_model=DoctorResponse)
async def update_doctor(
    doctor_id: UUID,
    payload: DoctorUpdateRequest,
    admin_user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Doctor:
    service = DoctorService(db)
    doctor = await service.update_doctor(doctor_id, **payload.model_dump(exclude_unset=True))
    await db.commit()
    return doctor


@router.post("/me/availability", response_model=AvailabilitySlotResponse, status_code=201)
async def create_my_availability(
    payload: AvailabilitySlotCreateRequest,
    current_user: Annotated[User, Depends(require_role(UserRole.DOCTOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AvailabilitySlot:
    service = DoctorService(db)
    doctor = await service.get_owned_doctor(current_user.id)
    slot = await service.create_slot(
        doctor,
        start_time=payload.start_time,
        end_time=payload.end_time,
    )
    await db.commit()
    return slot


@router.patch("/me/availability/{slot_id}", response_model=AvailabilitySlotResponse)
async def update_my_availability(
    slot_id: UUID,
    payload: AvailabilitySlotUpdateRequest,
    current_user: Annotated[User, Depends(require_role(UserRole.DOCTOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AvailabilitySlot:
    service = DoctorService(db)
    doctor = await service.get_owned_doctor(current_user.id)
    slot = await service.update_slot(doctor, slot_id, **payload.model_dump(exclude_unset=True))
    await db.commit()
    return slot


@router.delete("/me/availability/{slot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_availability(
    slot_id: UUID,
    current_user: Annotated[User, Depends(require_role(UserRole.DOCTOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    service = DoctorService(db)
    doctor = await service.get_owned_doctor(current_user.id)
    await service.delete_slot(doctor, slot_id)
    await db.commit()
