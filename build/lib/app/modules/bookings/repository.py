from __future__ import annotations

from uuid import UUID

from app.modules.bookings.models import AuditEvent, Booking, OutboxEvent
from app.modules.doctors.models import AvailabilitySlot
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


class BookingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_idempotency(self, patient_id: UUID, key: str) -> Booking | None:
        result = await self.session.execute(
            select(Booking).where(
                Booking.patient_id == patient_id,
                Booking.idempotency_key == key,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, booking_id: UUID) -> Booking | None:
        return await self.session.get(Booking, booking_id)

    async def get_by_id_for_update(self, booking_id: UUID) -> Booking | None:
        result = await self.session.execute(
            select(Booking).where(Booking.id == booking_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_slot_for_update(self, slot_id: UUID) -> AvailabilitySlot | None:
        result = await self.session.execute(
            select(AvailabilitySlot).where(AvailabilitySlot.id == slot_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self,
        *,
        patient_id: UUID | None = None,
        doctor_id: UUID | None = None,
        offset: int,
        limit: int,
    ) -> tuple[list[Booking], int]:
        filters = []
        if patient_id:
            filters.append(Booking.patient_id == patient_id)
        if doctor_id:
            filters.append(Booking.doctor_id == doctor_id)
        statement = select(Booking).where(*filters).order_by(Booking.created_at.desc())
        count = await self.session.scalar(select(func.count()).select_from(statement.subquery()))
        result = await self.session.execute(statement.offset(offset).limit(limit))
        return list(result.scalars().all()), int(count or 0)

    async def add_audit(
        self,
        *,
        actor_user_id: UUID | None,
        event_type: str,
        entity_type: str,
        entity_id: UUID,
        payload: str,
    ) -> None:
        self.session.add(
            AuditEvent(
                actor_user_id=actor_user_id,
                event_type=event_type,
                entity_type=entity_type,
                entity_id=entity_id,
                payload=payload,
            )
        )

    async def add_outbox(
        self,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: UUID,
        payload: str,
    ) -> None:
        self.session.add(
            OutboxEvent(
                event_type=event_type,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                payload=payload,
            )
        )
