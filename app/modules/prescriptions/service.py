from __future__ import annotations

import json
from uuid import UUID

from app.common.exceptions import AuthorizationError, ConflictError, ResourceNotFoundError
from app.modules.consultations.models import Consultation, ConsultationStatus
from app.modules.doctors.models import Doctor
from app.modules.prescriptions.models import Prescription
from app.modules.prescriptions.repository import PrescriptionRepository
from app.modules.users.models import User, UserRole
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


class PrescriptionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = PrescriptionRepository(session)

    async def create(
        self,
        *,
        consultation_id: UUID,
        actor: User,
        idempotency_key: str,
        medications: list[dict[str, object]],
        instructions: str | None,
    ) -> Prescription:
        existing = await self.repository.get_by_idempotency(consultation_id, idempotency_key)
        if existing is not None:
            return existing
        consultation = await self.session.get(Consultation, consultation_id)
        if consultation is None:
            raise ResourceNotFoundError("Consultation not found")
        doctor = await self.session.get(Doctor, consultation.doctor_id)
        if actor.role != UserRole.ADMIN and not (doctor and actor.id == doctor.user_id):
            raise AuthorizationError("Only the assigned doctor can create prescriptions")
        if consultation.status not in {
            ConsultationStatus.IN_PROGRESS,
            ConsultationStatus.COMPLETED,
        }:
            raise ConflictError("Prescriptions require an active or completed consultation")
        prescription = Prescription(
            consultation_id=consultation.id,
            doctor_id=consultation.doctor_id,
            patient_id=consultation.patient_id,
            idempotency_key=idempotency_key,
            medications=json.dumps(medications),
            instructions=instructions,
        )
        self.session.add(prescription)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            existing = await self.repository.get_by_idempotency(consultation_id, idempotency_key)
            if existing is not None:
                return existing
            raise ConflictError("Prescription already exists") from exc
        payload = json.dumps(
            {"prescription_id": str(prescription.id), "consultation_id": str(consultation.id)}
        )
        await self.repository.add_event(
            actor_user_id=actor.id,
            event_type="prescription.created",
            entity_id=prescription.id,
            payload=payload,
        )
        return prescription

    async def get(self, prescription_id: UUID, actor: User) -> Prescription:
        prescription = await self.repository.get_by_id(prescription_id)
        if prescription is None:
            raise ResourceNotFoundError("Prescription not found")
        doctor = await self.session.get(Doctor, prescription.doctor_id)
        if actor.role != UserRole.ADMIN and actor.id not in {
            prescription.patient_id,
            doctor.user_id if doctor else None,
        }:
            raise AuthorizationError("You are not authorized to access this prescription")
        return prescription
