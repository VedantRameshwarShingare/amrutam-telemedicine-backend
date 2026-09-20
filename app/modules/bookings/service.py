from __future__ import annotations

import json
import secrets
from uuid import UUID

from app.common.exceptions import AuthorizationError, ConflictError, ResourceNotFoundError
from app.core.redis import redis_client
from app.modules.bookings.models import Booking, BookingStatus
from app.modules.bookings.repository import BookingRepository
from app.modules.doctors.models import Doctor, DoctorStatus, SlotStatus
from app.modules.users.models import User
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


class BookingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = BookingRepository(session)

    async def create_booking(
        self,
        *,
        patient: User,
        slot_id: UUID,
        idempotency_key: str,
    ) -> Booking:
        patient_id = patient.id
        existing = await self.repository.get_by_idempotency(patient_id, idempotency_key)
        if existing is not None:
            if existing.slot_id != slot_id:
                raise ConflictError("Idempotency key was already used for another slot")
            return existing

        lock_key = f"booking:slot:{slot_id}"
        lock_token = secrets.token_urlsafe(24)
        lock_acquired = await self._acquire_redis_lock(lock_key, lock_token)
        try:
            slot = await self.repository.get_slot_for_update(slot_id)
            if slot is None:
                raise ResourceNotFoundError("Availability slot not found")
            if slot.status != SlotStatus.AVAILABLE:
                raise ConflictError("Availability slot is no longer available")

            doctor = await self.session.get(Doctor, slot.doctor_id)
            if doctor is None or doctor.status != DoctorStatus.ACTIVE:
                raise ConflictError("Doctor is not available for booking")

            booking = Booking(
                slot_id=slot.id,
                doctor_id=slot.doctor_id,
                patient_id=patient_id,
                status=BookingStatus.CONFIRMED,
                idempotency_key=idempotency_key,
            )
            slot.status = SlotStatus.BOOKED
            slot.version += 1
            self.session.add(booking)
            await self.session.flush()
            payload = json.dumps(
                {
                    "booking_id": str(booking.id),
                    "slot_id": str(slot.id),
                    "patient_id": str(patient_id),
                    "doctor_id": str(slot.doctor_id),
                }
            )
            await self.repository.add_audit(
                actor_user_id=patient_id,
                event_type="booking.created",
                entity_type="booking",
                entity_id=booking.id,
                payload=payload,
            )
            await self.repository.add_outbox(
                event_type="booking.created",
                aggregate_type="booking",
                aggregate_id=booking.id,
                payload=payload,
            )
            return booking
        except IntegrityError as exc:
            await self.session.rollback()
            existing = await self.repository.get_by_idempotency(patient_id, idempotency_key)
            if existing is not None:
                return existing
            raise ConflictError("Availability slot has already been booked") from exc
        finally:
            if lock_acquired:
                await self._release_redis_lock(lock_key, lock_token)

    async def cancel_booking(
        self,
        *,
        booking_id: UUID,
        actor: User,
        reason: str | None,
    ) -> Booking:
        booking = await self.repository.get_by_id_for_update(booking_id)
        if booking is None:
            raise ResourceNotFoundError("Booking not found")
        doctor = await self.session.get(Doctor, booking.doctor_id)
        if not self._can_manage(booking, actor, doctor.user_id if doctor else None):
            raise AuthorizationError("You are not authorized to manage this booking")
        if booking.status == BookingStatus.CANCELLED:
            return booking

        slot = await self.repository.get_slot_for_update(booking.slot_id)
        if slot is None:
            raise ResourceNotFoundError("Availability slot not found")
        if slot.status == SlotStatus.BOOKED:
            slot.status = SlotStatus.AVAILABLE
            slot.version += 1
        booking.status = BookingStatus.CANCELLED
        booking.cancellation_reason = reason
        booking.version += 1
        await self.session.flush()
        payload = json.dumps(
            {
                "booking_id": str(booking.id),
                "slot_id": str(booking.slot_id),
                "actor_user_id": str(actor.id),
                "reason": reason,
            }
        )
        await self.repository.add_audit(
            actor_user_id=actor.id,
            event_type="booking.cancelled",
            entity_type="booking",
            entity_id=booking.id,
            payload=payload,
        )
        await self.repository.add_outbox(
            event_type="booking.cancelled",
            aggregate_type="booking",
            aggregate_id=booking.id,
            payload=payload,
        )
        return booking

    @staticmethod
    def _can_manage(booking: Booking, actor: User, doctor_user_id: UUID | None) -> bool:
        return str(actor.role) == "ADMIN" or actor.id in {
            booking.patient_id,
            doctor_user_id,
        }

    async def _acquire_redis_lock(self, key: str, token: str) -> bool:
        try:
            acquired = await redis_client.set(key, token, nx=True, ex=30)
            if acquired:
                return True
            raise ConflictError("Booking is being processed by another request")
        except ConflictError:
            raise
        except Exception:
            return False

    async def _release_redis_lock(self, key: str, token: str) -> None:
        try:
            await redis_client.eval(
                "if redis.call('get', KEYS[1]) == ARGV[1] then "
                "return redis.call('del', KEYS[1]) else return 0 end",
                1,
                key,
                token,
            )
        except Exception:
            pass
