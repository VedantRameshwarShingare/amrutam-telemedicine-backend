from __future__ import annotations

import json
from uuid import UUID

from app.common.exceptions import AuthorizationError, ConflictError, ResourceNotFoundError
from app.modules.bookings.models import BookingStatus
from app.modules.consultations.models import Consultation, ConsultationStatus
from app.modules.consultations.repository import ConsultationRepository
from app.modules.doctors.models import Doctor
from app.modules.users.models import User, UserRole
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


class ConsultationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = ConsultationRepository(session)

    async def create(
        self,
        *,
        actor: User,
        booking_id: UUID,
        idempotency_key: str,
        clinical_notes: str | None,
    ) -> Consultation:
        existing = await self.repository.get_by_idempotency(actor.id, idempotency_key)
        if existing is not None:
            if existing.booking_id != booking_id:
                raise ConflictError("Idempotency key was already used for another booking")
            return existing
        booking = await self.repository.get_booking_for_update(booking_id)
        if booking is None:
            raise ResourceNotFoundError("Booking not found")
        if booking.status != BookingStatus.CONFIRMED:
            raise ConflictError("A consultation requires a confirmed booking")
        doctor = await self.session.get(Doctor, booking.doctor_id)
        if doctor is None:
            raise ResourceNotFoundError("Doctor not found")
        if not self._is_participant(actor, booking.patient_id, doctor.user_id):
            raise AuthorizationError("You are not a participant in this booking")
        existing_booking = await self.repository.get_by_booking(booking_id)
        if existing_booking is not None:
            if existing_booking.patient_id == actor.id:
                return existing_booking
            raise ConflictError("A consultation already exists for this booking")

        consultation = Consultation(
            booking_id=booking.id,
            doctor_id=booking.doctor_id,
            patient_id=booking.patient_id,
            idempotency_key=idempotency_key,
            clinical_notes=clinical_notes,
        )
        self.session.add(consultation)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            existing = await self.repository.get_by_booking(booking_id)
            if existing is not None:
                return existing
            raise ConflictError("Consultation already exists") from exc
        payload = json.dumps(
            {"consultation_id": str(consultation.id), "booking_id": str(booking.id)}
        )
        await self.repository.add_event(
            actor_user_id=actor.id,
            event_type="consultation.created",
            entity_id=consultation.id,
            payload=payload,
        )
        return consultation

    async def get(self, consultation_id: UUID) -> Consultation:
        consultation = await self.repository.get_by_id(consultation_id)
        if consultation is None:
            raise ResourceNotFoundError("Consultation not found")
        return consultation

    async def authorize_read(self, consultation: Consultation, actor: User) -> None:
        doctor = await self.session.get(Doctor, consultation.doctor_id)
        if actor.role == UserRole.ADMIN:
            return
        if actor.id == consultation.patient_id or (doctor and actor.id == doctor.user_id):
            return
        raise AuthorizationError("You are not authorized to access this consultation")

    async def update_status(
        self,
        *,
        consultation_id: UUID,
        actor: User,
        status: ConsultationStatus,
        clinical_notes: str | None,
    ) -> Consultation:
        consultation = await self.repository.get_for_update(consultation_id)
        if consultation is None:
            raise ResourceNotFoundError("Consultation not found")
        doctor = await self.session.get(Doctor, consultation.doctor_id)
        if actor.role != UserRole.ADMIN and not (doctor and actor.id == doctor.user_id):
            raise AuthorizationError(
                "Only the assigned doctor or admin can update consultation status"
            )
        allowed = {
            ConsultationStatus.SCHEDULED: {
                ConsultationStatus.IN_PROGRESS,
                ConsultationStatus.CANCELLED,
            },
            ConsultationStatus.IN_PROGRESS: {
                ConsultationStatus.COMPLETED,
                ConsultationStatus.CANCELLED,
            },
            ConsultationStatus.COMPLETED: set(),
            ConsultationStatus.CANCELLED: set(),
        }
        if status not in allowed[consultation.status]:
            raise ConflictError("Invalid consultation status transition")
        consultation.status = status
        if clinical_notes is not None:
            consultation.clinical_notes = clinical_notes
        consultation.version += 1
        await self.session.flush()
        payload = json.dumps({"consultation_id": str(consultation.id), "status": status.value})
        await self.repository.add_event(
            actor_user_id=actor.id,
            event_type="consultation.status_changed",
            entity_id=consultation.id,
            payload=payload,
        )
        return consultation

    @staticmethod
    def _is_participant(actor: User, patient_id: UUID, doctor_user_id: UUID) -> bool:
        return actor.role in {UserRole.PATIENT, UserRole.DOCTOR} and actor.id in {
            patient_id,
            doctor_user_id,
        }
