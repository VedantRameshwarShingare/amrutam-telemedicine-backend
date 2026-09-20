from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import anyio
from app.core.database import AsyncSessionLocal
from app.modules.bookings.models import AuditEvent, OutboxEvent
from app.modules.payments.provider import PaymentProvider, ProviderChargeResult
from app.modules.payments.service import PaymentService
from app.modules.users.models import User
from sqlalchemy import func, select
from tests.test_bookings import register, setup_slot


def test_payment_success_idempotency_and_events(client):
    _, patient, slot = setup_slot(client, "payment01")
    headers = {"Authorization": f"Bearer {patient['access_token']}"}
    payload = {
        "booking_id": slot["booking_id"] if "booking_id" in slot else "",
        "idempotency_key": "payment-key-01",
    }
    booking_response = client.post(
        "/api/v1/bookings",
        headers=headers,
        json={"slot_id": slot["id"], "idempotency_key": "payment-booking-01"},
    )
    assert booking_response.status_code == 201
    payload["booking_id"] = booking_response.json()["id"]

    first = client.post("/api/v1/payments", headers=headers, json=payload)
    replay = client.post("/api/v1/payments", headers=headers, json=payload)

    assert first.status_code == 201, first.text
    assert first.json()["status"] == "SUCCEEDED"
    assert replay.status_code == 201
    assert replay.json()["id"] == first.json()["id"]

    async def counts() -> tuple[int, int]:
        async with AsyncSessionLocal() as session:
            audit = await session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.event_type == "payment.succeeded")
            )
            outbox = await session.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.event_type == "payment.succeeded")
            )
            return int(audit or 0), int(outbox or 0)

    assert anyio.run(counts) == (1, 1)


def test_payment_provider_failure_is_persisted(client):
    _, patient, slot = setup_slot(client, "payment02")
    headers = {"Authorization": f"Bearer {patient['access_token']}"}
    booking = client.post(
        "/api/v1/bookings",
        headers=headers,
        json={"slot_id": slot["id"], "idempotency_key": "payment-booking-02"},
    ).json()
    response = client.post(
        "/api/v1/payments",
        headers=headers,
        json={"booking_id": booking["id"], "idempotency_key": "fail-payment-02"},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "FAILED"
    assert response.json()["failure_code"] == "MOCK_DECLINED"


def test_payment_idempotency_key_cannot_change_booking(client):
    doctor, patient, first_slot = setup_slot(client, "payment02-key")
    headers = {"Authorization": f"Bearer {patient['access_token']}"}
    second_start = datetime.now(UTC).replace(microsecond=0) + timedelta(days=4)
    second_slot_response = client.post(
        "/api/v1/doctors/me/availability",
        headers={"Authorization": f"Bearer {doctor['access_token']}"},
        json={
            "start_time": second_start.isoformat(),
            "end_time": (second_start + timedelta(hours=1)).isoformat(),
        },
    )
    assert second_slot_response.status_code == 201, second_slot_response.text
    second_slot = second_slot_response.json()
    first_booking = client.post(
        "/api/v1/bookings",
        headers=headers,
        json={"slot_id": first_slot["id"], "idempotency_key": "payment-booking-key-1"},
    ).json()
    second_booking = client.post(
        "/api/v1/bookings",
        headers=headers,
        json={"slot_id": second_slot["id"], "idempotency_key": "payment-booking-key-2"},
    ).json()

    first = client.post(
        "/api/v1/payments",
        headers=headers,
        json={"booking_id": first_booking["id"], "idempotency_key": "payment-reused-key"},
    )
    replay_for_other_booking = client.post(
        "/api/v1/payments",
        headers=headers,
        json={"booking_id": second_booking["id"], "idempotency_key": "payment-reused-key"},
    )

    assert first.status_code == 201
    assert replay_for_other_booking.status_code == 409


def test_payment_authorization_rejects_other_patient(client):
    _, patient, slot = setup_slot(client, "payment03")
    other = register(client, "payment-other@example.com", "+155599911", "PATIENT")
    booking = client.post(
        "/api/v1/bookings",
        headers={"Authorization": f"Bearer {patient['access_token']}"},
        json={"slot_id": slot["id"], "idempotency_key": "payment-booking-03"},
    ).json()
    response = client.post(
        "/api/v1/payments",
        headers={"Authorization": f"Bearer {other['access_token']}"},
        json={"booking_id": booking["id"], "idempotency_key": "payment-key-03"},
    )
    assert response.status_code == 403


class BoundaryProvider(PaymentProvider):
    def __init__(self, session):
        self.session = session
        self.was_in_transaction = True

    async def charge(self, *, amount, currency, idempotency_key):
        self.was_in_transaction = self.session.in_transaction()
        return ProviderChargeResult(provider_payment_id="boundary-provider-id", succeeded=True)


def test_provider_call_is_outside_database_transaction(client):
    _, patient, slot = setup_slot(client, "payment04")
    booking = client.post(
        "/api/v1/bookings",
        headers={"Authorization": f"Bearer {patient['access_token']}"},
        json={"slot_id": slot["id"], "idempotency_key": "payment-booking-04"},
    ).json()

    async def run() -> bool:
        async with AsyncSessionLocal() as session:
            user = await session.get(User, UUID(patient["user_id"]))
            assert user is not None
            provider = BoundaryProvider(session)
            payment = await PaymentService(session, provider=provider).create_payment(
                patient=user,
                booking_id=UUID(booking["id"]),
                currency="INR",
                idempotency_key="payment-key-04",
            )
            assert payment.status.value == "SUCCEEDED"
            return provider.was_in_transaction

    assert anyio.run(run) is False
