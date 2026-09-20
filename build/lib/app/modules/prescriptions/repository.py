from __future__ import annotations

from uuid import UUID

from app.modules.bookings.models import AuditEvent, OutboxEvent
from app.modules.prescriptions.models import Prescription
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class PrescriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_idempotency(self, consultation_id: UUID, key: str) -> Prescription | None:
        result = await self.session.execute(
            select(Prescription).where(
                Prescription.consultation_id == consultation_id,
                Prescription.idempotency_key == key,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, prescription_id: UUID) -> Prescription | None:
        return await self.session.get(Prescription, prescription_id)

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
                entity_type="prescription",
                entity_id=entity_id,
                payload=payload,
            )
        )
        self.session.add(
            OutboxEvent(
                event_type=event_type,
                aggregate_type="prescription",
                aggregate_id=entity_id,
                payload=payload,
            )
        )
