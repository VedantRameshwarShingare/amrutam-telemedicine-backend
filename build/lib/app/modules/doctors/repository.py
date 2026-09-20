from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.modules.doctors.models import AvailabilitySlot, Doctor, SlotStatus
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession


class DoctorRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, doctor_id: UUID) -> Doctor | None:
        return await self.session.get(Doctor, doctor_id)

    async def get_by_user_id(self, user_id: UUID) -> Doctor | None:
        result = await self.session.execute(select(Doctor).where(Doctor.user_id == user_id))
        return result.scalar_one_or_none()

    async def get_by_license(self, license_number: str) -> Doctor | None:
        result = await self.session.execute(
            select(Doctor).where(Doctor.license_number == license_number)
        )
        return result.scalar_one_or_none()

    async def list_doctors(
        self,
        *,
        specialization: str | None,
        experience_min: int | None,
        availability_start: datetime | None,
        availability_end: datetime | None,
        offset: int,
        limit: int,
        sort_by: str,
        sort_desc: bool,
    ) -> tuple[list[Doctor], int]:
        filters = [Doctor.status == "ACTIVE"]
        if specialization:
            filters.append(func.lower(Doctor.specialization) == specialization.lower())
        if experience_min is not None:
            filters.append(Doctor.experience_years >= experience_min)
        if availability_start and availability_end:
            filters.append(
                select(AvailabilitySlot.id)
                .where(
                    AvailabilitySlot.doctor_id == Doctor.id,
                    AvailabilitySlot.status == SlotStatus.AVAILABLE,
                    AvailabilitySlot.start_time < availability_end,
                    AvailabilitySlot.end_time > availability_start,
                )
                .exists()
            )

        sort_column = {
            "created_at": Doctor.created_at,
            "experience_years": Doctor.experience_years,
            "consultation_fee": Doctor.consultation_fee,
            "specialization": Doctor.specialization,
        }[sort_by]
        order = sort_column.desc() if sort_desc else sort_column.asc()
        base = select(Doctor).where(and_(*filters))
        count_result = await self.session.execute(
            select(func.count()).select_from(base.order_by(None).subquery())
        )
        result = await self.session.execute(base.order_by(order).offset(offset).limit(limit))
        return list(result.scalars().all()), int(count_result.scalar_one())

    async def get_slot(self, slot_id: UUID) -> AvailabilitySlot | None:
        return await self.session.get(AvailabilitySlot, slot_id)

    async def list_slots(
        self,
        doctor_id: UUID,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[AvailabilitySlot]:
        filters = [AvailabilitySlot.doctor_id == doctor_id]
        if start:
            filters.append(AvailabilitySlot.start_time >= start)
        if end:
            filters.append(AvailabilitySlot.end_time <= end)
        result = await self.session.execute(
            select(AvailabilitySlot)
            .where(and_(*filters))
            .order_by(AvailabilitySlot.start_time)
        )
        return list(result.scalars().all())

    async def has_overlap(
        self,
        doctor_id: UUID,
        start_time: datetime,
        end_time: datetime,
        *,
        exclude_slot_id: UUID | None = None,
    ) -> bool:
        filters = [
            AvailabilitySlot.doctor_id == doctor_id,
            AvailabilitySlot.status != SlotStatus.CANCELLED,
            AvailabilitySlot.start_time < end_time,
            AvailabilitySlot.end_time > start_time,
        ]
        if exclude_slot_id:
            filters.append(AvailabilitySlot.id != exclude_slot_id)
        result = await self.session.execute(
            select(AvailabilitySlot.id).where(and_(*filters)).limit(1)
        )
        return result.scalar_one_or_none() is not None
