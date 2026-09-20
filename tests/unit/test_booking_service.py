from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from app.modules.bookings.service import BookingService
from app.modules.doctors.models import DoctorStatus, SlotStatus
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.unit


class ExpiringPatient:
    def __init__(self, patient_id: UUID) -> None:
        self._patient_id = patient_id
        self.access_count = 0

    @property
    def id(self) -> UUID:
        self.access_count += 1
        if self.access_count > 2:
            raise AssertionError("patient.id was accessed after rollback recovery started")
        return self._patient_id


class FakeRepository:
    def __init__(self, slot_id: UUID, doctor_id: UUID) -> None:
        self.slot_id = slot_id
        self.doctor_id = doctor_id
        self.lookup_count = 0
        self.existing_booking = SimpleNamespace(slot_id=slot_id)

    async def get_by_idempotency(self, patient_id: UUID, key: str):
        self.lookup_count += 1
        return None if self.lookup_count == 1 else self.existing_booking

    async def get_slot_for_update(self, slot_id: UUID):
        return SimpleNamespace(
            id=slot_id,
            doctor_id=self.doctor_id,
            status=SlotStatus.AVAILABLE,
            version=1,
        )

    async def add_audit(self, **kwargs) -> None:
        raise AssertionError("audit event should not be created after a failed flush")

    async def add_outbox(self, **kwargs) -> None:
        raise AssertionError("outbox event should not be created after a failed flush")


class FakeSession:
    def add(self, instance) -> None:
        self.instance = instance

    async def flush(self) -> None:
        raise IntegrityError("INSERT INTO bookings", {}, Exception("slot already booked"))

    async def rollback(self) -> None:
        self.rolled_back = True

    async def get(self, model, doctor_id: UUID):
        return SimpleNamespace(id=doctor_id, status=DoctorStatus.ACTIVE)


@pytest.mark.asyncio
async def test_create_booking_uses_cached_patient_id_after_integrity_error():
    slot_id = uuid4()
    patient = ExpiringPatient(uuid4())
    service = BookingService(FakeSession())
    service.repository = FakeRepository(slot_id=slot_id, doctor_id=uuid4())

    async def no_lock(*args, **kwargs) -> bool:
        return False

    service._acquire_redis_lock = no_lock

    booking = await service.create_booking(
        patient=patient,
        slot_id=slot_id,
        idempotency_key="duplicate-booking-key",
    )

    assert booking is service.repository.existing_booking
    assert patient.access_count == 1
