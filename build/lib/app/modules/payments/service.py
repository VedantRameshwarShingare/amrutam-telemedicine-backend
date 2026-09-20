from __future__ import annotations

import json
import secrets
from decimal import Decimal
from uuid import UUID

from app.common.exceptions import AuthorizationError, ConflictError, ResourceNotFoundError
from app.core.redis import redis_client
from app.modules.bookings.models import BookingStatus
from app.modules.doctors.models import Doctor
from app.modules.payments.models import Payment, PaymentStatus
from app.modules.payments.provider import MockPaymentProvider, PaymentProvider
from app.modules.payments.repository import PaymentRepository
from app.modules.users.models import User, UserRole
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


class PaymentService:
    def __init__(self, session: AsyncSession, provider: PaymentProvider | None = None) -> None:
        self.session = session
        self.repository = PaymentRepository(session)
        self.provider = provider or MockPaymentProvider()

    async def create_payment(
        self,
        *,
        patient: User,
        booking_id: UUID,
        currency: str,
        idempotency_key: str,
    ) -> Payment:
        existing = await self.repository.get_by_idempotency(patient.id, idempotency_key)
        if existing is not None:
            if existing.booking_id != booking_id:
                raise ConflictError("Idempotency key was already used for another booking")
            return existing

        lock_key = f"payment:booking:{booking_id}"
        lock_token = secrets.token_urlsafe(24)
        acquired = await self._acquire_lock(lock_key, lock_token)
        try:
            booking = await self.repository.get_booking_for_update(booking_id)
            if booking is None:
                raise ResourceNotFoundError("Booking not found")
            if booking.patient_id != patient.id:
                raise AuthorizationError("You are not authorized to pay for this booking")
            if booking.status != BookingStatus.CONFIRMED:
                raise ConflictError("Only confirmed bookings can be paid")
            existing_booking_payment = await self.repository.get_by_booking(booking_id)
            if existing_booking_payment is not None:
                if existing_booking_payment.patient_id == patient.id:
                    return existing_booking_payment
                raise ConflictError("A payment already exists for this booking")
            doctor = await self.session.get(Doctor, booking.doctor_id)
            if doctor is None:
                raise ResourceNotFoundError("Doctor not found")

            payment = Payment(
                booking_id=booking.id,
                patient_id=patient.id,
                amount=Decimal(str(doctor.consultation_fee)),
                currency=currency.upper(),
                status=PaymentStatus.PROCESSING,
                provider="mock",
                idempotency_key=idempotency_key,
            )
            self.session.add(payment)
            try:
                await self.session.flush()
            except IntegrityError as exc:
                await self.session.rollback()
                existing = await self.repository.get_by_idempotency(patient.id, idempotency_key)
                if existing is not None:
                    return existing
                raise ConflictError("Payment already exists for this booking") from exc
            await self.session.commit()
        finally:
            if acquired:
                await self._release_lock(lock_key, lock_token)

        # The provider call deliberately happens after commit and outside any DB transaction.
        try:
            result = await self.provider.charge(
                amount=payment.amount,
                currency=payment.currency,
                idempotency_key=idempotency_key,
            )
        except Exception as exc:
            return await self._finalize(
                payment.id,
                patient.id,
                PaymentStatus.FAILED,
                failure_code="PROVIDER_ERROR",
                failure_message=str(exc),
            )
        if result.succeeded:
            return await self._finalize(
                payment.id,
                patient.id,
                PaymentStatus.SUCCEEDED,
                provider_payment_id=result.provider_payment_id,
            )
        return await self._finalize(
            payment.id,
            patient.id,
            PaymentStatus.FAILED,
            provider_payment_id=result.provider_payment_id,
            failure_code=result.failure_code,
            failure_message=result.failure_message,
        )

    async def _finalize(
        self,
        payment_id: UUID,
        actor_user_id: UUID,
        status: PaymentStatus,
        *,
        provider_payment_id: str | None = None,
        failure_code: str | None = None,
        failure_message: str | None = None,
    ) -> Payment:
        payment = await self.repository.get_for_update(payment_id)
        if payment is None:
            raise ResourceNotFoundError("Payment not found")
        if payment.status in {PaymentStatus.SUCCEEDED, PaymentStatus.FAILED}:
            return payment
        payment.status = status
        payment.provider_payment_id = provider_payment_id
        payment.failure_code = failure_code
        payment.failure_message = failure_message
        payment.version += 1
        await self.session.flush()
        payload = json.dumps(
            {
                "payment_id": str(payment.id),
                "booking_id": str(payment.booking_id),
                "status": status.value,
                "provider_payment_id": provider_payment_id,
            }
        )
        await self.repository.add_event(
            actor_user_id=actor_user_id,
            event_type=f"payment.{status.value.lower()}",
            entity_id=payment.id,
            payload=payload,
        )
        await self.session.commit()
        return payment

    async def get_payment(self, payment_id: UUID, actor: User) -> Payment:
        payment = await self.repository.get_by_id(payment_id)
        if payment is None:
            raise ResourceNotFoundError("Payment not found")
        if actor.role == UserRole.ADMIN or payment.patient_id == actor.id:
            return payment
        raise AuthorizationError("You are not authorized to access this payment")

    async def _acquire_lock(self, key: str, token: str) -> bool:
        try:
            acquired = await redis_client.set(key, token, nx=True, ex=30)
            if acquired:
                return True
            raise ConflictError("Payment is being processed by another request")
        except ConflictError:
            raise
        except Exception:
            return False

    async def _release_lock(self, key: str, token: str) -> None:
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
