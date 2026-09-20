from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import anyio
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.modules.bookings.models import AuditEvent, Booking, OutboxEvent
from app.modules.users.models import User, UserRole
from sqlalchemy import func, select


def register(client, email: str, phone: str, role: str) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "phone": phone,
            "password": "StrongPass123!",
            "role": role,
        },
    )
    assert response.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "StrongPass123!"},
    )
    assert login.status_code == 200
    tokens = login.json()
    profile = client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    tokens["user_id"] = profile.json()["id"]
    return tokens


def create_admin() -> tuple[str, str]:
    async def create() -> tuple[str, str]:
        async with AsyncSessionLocal() as session:
            admin = User(
                email="booking-admin@example.com",
                phone="+15558880000",
                password_hash=hash_password("StrongPass123!"),
                role=UserRole.ADMIN,
                is_active=True,
            )
            session.add(admin)
            await session.commit()
            return str(admin.id), admin.email

    return anyio.run(create)


def setup_slot(client, suffix: str = "") -> tuple[dict, dict, dict]:
    doctor = register(
        client, f"booking-doctor{suffix}@example.com", f"+1555777{suffix or '01'}", "DOCTOR"
    )
    patient = register(
        client, f"booking-patient{suffix}@example.com", f"+1555778{suffix or '01'}", "PATIENT"
    )
    _, admin_email = create_admin()
    admin_login = client.post(
        "/api/v1/auth/login",
        json={"email": admin_email, "password": "StrongPass123!"},
    )
    profile = client.post(
        "/api/v1/doctors",
        headers={"Authorization": f"Bearer {admin_login.json()['access_token']}"},
        json={
            "user_id": doctor["user_id"],
            "license_number": f"BOOK-LIC-{suffix or '01'}",
            "specialization": "General Medicine",
            "experience_years": 8,
            "consultation_fee": "50.00",
        },
    )
    assert profile.status_code == 201, profile.text
    start = datetime.now(UTC).replace(microsecond=0) + timedelta(days=3)
    slot_response = client.post(
        "/api/v1/doctors/me/availability",
        headers={"Authorization": f"Bearer {doctor['access_token']}"},
        json={
            "start_time": start.isoformat(),
            "end_time": (start + timedelta(hours=1)).isoformat(),
        },
    )
    assert slot_response.status_code == 201, slot_response.text
    return doctor, patient, slot_response.json()


def test_booking_idempotency_and_slot_state(client):
    _, patient, slot = setup_slot(client)
    headers = {"Authorization": f"Bearer {patient['access_token']}"}
    payload = {"slot_id": slot["id"], "idempotency_key": "same-booking-key"}

    first = client.post("/api/v1/bookings", headers=headers, json=payload)
    replay = client.post("/api/v1/bookings", headers=headers, json=payload)

    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json()["id"] == first.json()["id"]
    availability = client.get(f"/api/v1/doctors/{slot['doctor_id']}/availability", headers=headers)
    assert availability.json()[0]["status"] == "BOOKED"


def test_booking_rejects_second_patient_and_emits_events(client):
    doctor, patient, slot = setup_slot(client, "02")
    other = register(client, "booking-other@example.com", "+155577899", "PATIENT")
    first = client.post(
        "/api/v1/bookings",
        headers={"Authorization": f"Bearer {patient['access_token']}"},
        json={"slot_id": slot["id"], "idempotency_key": "patient-booking-02"},
    )
    second = client.post(
        "/api/v1/bookings",
        headers={"Authorization": f"Bearer {other['access_token']}"},
        json={"slot_id": slot["id"], "idempotency_key": "other-booking-02"},
    )
    assert first.status_code == 201
    assert second.status_code == 409

    async def counts() -> tuple[int, int]:
        async with AsyncSessionLocal() as session:
            audit = await session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.event_type == "booking.created")
            )
            outbox = await session.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.event_type == "booking.created")
            )
            return int(audit or 0), int(outbox or 0)

    audit_count, outbox_count = anyio.run(counts)
    assert audit_count == 1
    assert outbox_count == 1


def test_booking_cancellation_restores_slot_and_is_authorized(client):
    doctor, patient, slot = setup_slot(client, "03")
    booking = client.post(
        "/api/v1/bookings",
        headers={"Authorization": f"Bearer {patient['access_token']}"},
        json={"slot_id": slot["id"], "idempotency_key": "cancel-booking-03"},
    ).json()
    unauthorized = register(client, "booking-unauthorized@example.com", "+155577899", "PATIENT")
    denied = client.post(
        f"/api/v1/bookings/{booking['id']}/cancel",
        headers={"Authorization": f"Bearer {unauthorized['access_token']}"},
        json={"reason": "not mine"},
    )
    assert denied.status_code == 403

    cancelled = client.post(
        f"/api/v1/bookings/{booking['id']}/cancel",
        headers={"Authorization": f"Bearer {patient['access_token']}"},
        json={"reason": "schedule changed"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
    availability = client.get(
        f"/api/v1/doctors/{slot['doctor_id']}/availability",
        headers={"Authorization": f"Bearer {doctor['access_token']}"},
    )
    assert availability.json()[0]["status"] == "AVAILABLE"


def test_booking_concurrency_never_creates_two_bookings(client):
    _, patient, slot = setup_slot(client, "04")
    headers = {"Authorization": f"Bearer {patient['access_token']}"}
    payloads = [
        {"slot_id": slot["id"], "idempotency_key": "concurrent-key-a"},
        {"slot_id": slot["id"], "idempotency_key": "concurrent-key-b"},
    ]
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(
                lambda payload: client.post(
                    "/api/v1/bookings", headers=headers, json=payload
                ),
                payloads,
            )
        )
    assert sum(response.status_code == 201 for response in responses) == 1
    assert sum(response.status_code == 409 for response in responses) == 1

    async def count_bookings() -> int:
        async with AsyncSessionLocal() as session:
            return int(await session.scalar(select(func.count()).select_from(Booking)) or 0)

    assert anyio.run(count_bookings) == 1


def test_booking_idempotency_key_cannot_change_slot(client):
    doctor, patient, first_slot = setup_slot(client, "05")
    start = datetime.now(UTC).replace(microsecond=0) + timedelta(days=5)
    second_slot_response = client.post(
        "/api/v1/doctors/me/availability",
        headers={"Authorization": f"Bearer {doctor['access_token']}"},
        json={
            "start_time": start.isoformat(),
            "end_time": (start + timedelta(hours=1)).isoformat(),
        },
    )
    assert second_slot_response.status_code == 201
    second_slot = second_slot_response.json()
    headers = {"Authorization": f"Bearer {patient['access_token']}"}

    first = client.post(
        "/api/v1/bookings",
        headers=headers,
        json={"slot_id": first_slot["id"], "idempotency_key": "same-key-different-slot"},
    )
    second = client.post(
        "/api/v1/bookings",
        headers=headers,
        json={"slot_id": second_slot["id"], "idempotency_key": "same-key-different-slot"},
    )

    assert first.status_code == 201
    assert second.status_code == 409
