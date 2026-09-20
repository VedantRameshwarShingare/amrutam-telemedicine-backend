from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from app.common.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.redis import redis_client
from app.modules.doctors.models import AvailabilitySlot, Doctor, DoctorStatus, SlotStatus
from app.modules.doctors.repository import DoctorRepository
from app.modules.users.models import User, UserRole
from sqlalchemy.ext.asyncio import AsyncSession


class DoctorService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = DoctorRepository(session)

    async def create_doctor(
        self,
        *,
        user: User | None,
        user_id: UUID,
        license_number: str,
        specialization: str,
        experience_years: int,
        consultation_fee: Decimal,
        status: DoctorStatus,
    ) -> Doctor:
        if user is None or user.role != UserRole.DOCTOR:
            raise ValidationError("Doctor profile requires a user with DOCTOR role")
        if await self.repository.get_by_user_id(user_id):
            raise ConflictError("Doctor profile already exists for this user")
        if await self.repository.get_by_license(license_number):
            raise ConflictError("License number already exists")
        doctor = Doctor(
            user_id=user_id,
            license_number=license_number,
            specialization=specialization,
            experience_years=experience_years,
            consultation_fee=consultation_fee,
            status=status,
        )
        self.session.add(doctor)
        await self.session.flush()
        return doctor

    async def get_doctor(self, doctor_id: UUID) -> Doctor:
        doctor = await self.repository.get_by_id(doctor_id)
        if doctor is None:
            raise ResourceNotFoundError("Doctor not found")
        return doctor

    async def list_doctors(self, **kwargs: object) -> tuple[list[Doctor], int]:
        return await self.repository.list_doctors(**kwargs)  # type: ignore[arg-type]

    async def update_doctor(self, doctor_id: UUID, **changes: object) -> Doctor:
        doctor = await self.get_doctor(doctor_id)
        for field, value in changes.items():
            if value is not None:
                setattr(doctor, field, value)
        await self.session.flush()
        await self._invalidate_doctor_cache(doctor_id)
        return doctor

    async def create_slot(
        self,
        doctor: Doctor,
        *,
        start_time: datetime,
        end_time: datetime,
    ) -> AvailabilitySlot:
        start_time, end_time = self._normalize_times(start_time, end_time)
        if await self.repository.has_overlap(doctor.id, start_time, end_time):
            raise ConflictError("Availability slot overlaps an existing slot")
        slot = AvailabilitySlot(
            doctor_id=doctor.id,
            start_time=start_time,
            end_time=end_time,
            status=SlotStatus.AVAILABLE,
        )
        self.session.add(slot)
        await self.session.flush()
        await self._invalidate_availability_cache(doctor.id)
        return slot

    async def update_slot(
        self,
        doctor: Doctor,
        slot_id: UUID,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        status: SlotStatus | None = None,
    ) -> AvailabilitySlot:
        slot = await self.repository.get_slot(slot_id)
        if slot is None or slot.doctor_id != doctor.id:
            raise ResourceNotFoundError("Availability slot not found")
        new_start = start_time or slot.start_time
        new_end = end_time or slot.end_time
        if start_time is None and new_start.tzinfo is None:
            new_start = new_start.replace(tzinfo=UTC)
        if end_time is None and new_end.tzinfo is None:
            new_end = new_end.replace(tzinfo=UTC)
        new_start, new_end = self._normalize_times(new_start, new_end)
        if await self.repository.has_overlap(
            doctor.id, new_start, new_end, exclude_slot_id=slot.id
        ):
            raise ConflictError("Availability slot overlaps an existing slot")
        slot.start_time = new_start
        slot.end_time = new_end
        if status is not None:
            slot.status = status
        slot.version += 1
        await self.session.flush()
        await self._invalidate_availability_cache(doctor.id)
        return slot

    async def delete_slot(self, doctor: Doctor, slot_id: UUID) -> None:
        slot = await self.repository.get_slot(slot_id)
        if slot is None or slot.doctor_id != doctor.id:
            raise ResourceNotFoundError("Availability slot not found")
        if slot.status in {SlotStatus.BOOKED, SlotStatus.HELD}:
            raise ConflictError("Booked or held slots cannot be deleted")
        slot.status = SlotStatus.CANCELLED
        slot.version += 1
        await self.session.flush()
        await self._invalidate_availability_cache(doctor.id)

    async def list_availability(
        self,
        doctor_id: UUID,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[AvailabilitySlot]:
        return await self.repository.list_slots(doctor_id, start=start, end=end)

    async def get_owned_doctor(self, user_id: UUID) -> Doctor:
        doctor = await self.repository.get_by_user_id(user_id)
        if doctor is None:
            raise ResourceNotFoundError("Doctor profile not found")
        return doctor

    @staticmethod
    def _normalize_times(start_time: datetime, end_time: datetime) -> tuple[datetime, datetime]:
        if start_time.tzinfo is None or end_time.tzinfo is None:
            raise ValidationError("Slot times must include a timezone")
        start_time = start_time.astimezone(UTC)
        end_time = end_time.astimezone(UTC)
        if start_time >= end_time:
            raise ValidationError("Slot start_time must be before end_time")
        return start_time, end_time

    async def _invalidate_doctor_cache(self, doctor_id: UUID) -> None:
        try:
            await redis_client.delete(f"doctor:{doctor_id}")
        except Exception:
            pass

    async def _invalidate_availability_cache(self, doctor_id: UUID) -> None:
        try:
            await redis_client.delete(f"doctor:{doctor_id}:availability")
        except Exception:
            pass

    async def get_cached_doctor(self, doctor_id: UUID) -> dict[str, object] | None:
        try:
            cached = await redis_client.get(f"doctor:{doctor_id}")
            return json.loads(cached) if cached else None
        except Exception:
            return None

    async def cache_doctor(self, doctor: Doctor) -> None:
        payload = {
            "id": str(doctor.id),
            "user_id": str(doctor.user_id),
            "license_number": doctor.license_number,
            "specialization": doctor.specialization,
            "experience_years": doctor.experience_years,
            "consultation_fee": str(doctor.consultation_fee),
            "status": (
                doctor.status.value if hasattr(doctor.status, "value") else str(doctor.status)
            ),
            "created_at": doctor.created_at.isoformat(),
            "updated_at": doctor.updated_at.isoformat(),
        }
        try:
            await redis_client.set(f"doctor:{doctor.id}", json.dumps(payload), ex=300)
        except Exception:
            pass
