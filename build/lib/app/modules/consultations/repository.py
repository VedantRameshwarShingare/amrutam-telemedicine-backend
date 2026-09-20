from __future__ import annotations

from uuid import UUID

from app.modules.bookings.models import AuditEvent, Booking, OutboxEvent
from app.modules.consultations.models import Consultation
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class ConsultationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_idempotency(self, patient_id: UUID, key: str) -> Consultation | None:
        result = await self.session.execute(
            select(Consultation).where(
                Consultation.patient_id == patient_id,
                Consultation.idempotency_key == key,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_booking(self, booking_id: UUID) -> Consultation | None:
        result = await self.session.execute(
            select(Consultation).where(Consultation.booking_id == booking_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, consultation_id: UUID) -> Consultation | None:
        return await self.session.get(Consultation, consultation_id)

    async def get_for_update(self, consultation_id: UUID) -> Consultation | None:
        result = await self.session.execute(
            select(Consultation).where(Consultation.id == consultation_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_booking_for_update(self, booking_id: UUID) -> Booking | None:
        result = await self.session.execute(
            select(Booking).where(Booking.id == booking_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def add_event(
        self,
        *,
        actor_user_id: UUID,
        event_type: str,
        entity_id: UUID,
        payload: str,
    ) -> None:
        self.session.add(
            AuditEvent(
                actor_user_id=actor_user_id,
                event_type=event_type,
                entity_type="consultation",
                entity_id=entity_id,
                payload=payload,
            )
        )
        self.session.add(
            OutboxEvent(
                event_type=event_type,
                aggregate_type="consultation",
                aggregate_id=entity_id,
                payload=payload,
            )
        )
