from __future__ import annotations

from uuid import UUID

from app.modules.bookings.models import AuditEvent, Booking, OutboxEvent
from app.modules.payments.models import Payment
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class PaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_idempotency(self, patient_id: UUID, key: str) -> Payment | None:
        result = await self.session.execute(
            select(Payment).where(
                Payment.patient_id == patient_id,
                Payment.idempotency_key == key,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_booking(self, booking_id: UUID) -> Payment | None:
        result = await self.session.execute(select(Payment).where(Payment.booking_id == booking_id))
        return result.scalar_one_or_none()

    async def get_by_id(self, payment_id: UUID) -> Payment | None:
        return await self.session.get(Payment, payment_id)

    async def get_for_update(self, payment_id: UUID) -> Payment | None:
        result = await self.session.execute(
            select(Payment).where(Payment.id == payment_id).with_for_update()
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
                entity_type="payment",
                entity_id=entity_id,
                payload=payload,
            )
        )
        self.session.add(
            OutboxEvent(
                event_type=event_type,
                aggregate_type="payment",
                aggregate_id=entity_id,
                payload=payload,
            )
        )
