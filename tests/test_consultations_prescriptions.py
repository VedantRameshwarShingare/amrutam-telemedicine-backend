from __future__ import annotations

from datetime import UTC, datetime, timedelta

import anyio
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.modules.bookings.models import AuditEvent, OutboxEvent
from app.modules.users.models import User, UserRole
from sqlalchemy import func, select


def register(client, email: str, phone: str, role: str) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "phone": phone, "password": "StrongPass123!", "role": role},
    )
    assert response.status_code == 201, response.text
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "StrongPass123!"})
    tokens = login.json()
    profile = client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    tokens["user_id"] = profile.json()["id"]
    return tokens


def create_admin(client, suffix: str) -> dict:
    async def create() -> None:
        async with AsyncSessionLocal() as session:
            session.add(
                User(
                    email=f"phase5-admin{suffix}@example.com",
                    phone=f"+1555666{suffix}",
                    password_hash=hash_password("StrongPass123!"),
                    role=UserRole.ADMIN,
                    is_active=True,
                )
            )
            await session.commit()

    anyio.run(create)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": f"phase5-admin{suffix}@example.com", "password": "StrongPass123!"},
    )
    return login.json()


def setup_consultation(client, suffix: str = "01") -> tuple[dict, dict, dict]:
    doctor = register(client, f"phase5-doctor{suffix}@example.com", f"+1555001{suffix}", "DOCTOR")
    patient = register(
        client, f"phase5-patient{suffix}@example.com", f"+1555002{suffix}", "PATIENT"
    )
    admin = create_admin(client, suffix)
    profile = client.post(
        "/api/v1/doctors",
        headers={"Authorization": f"Bearer {admin['access_token']}"},
        json={
            "user_id": doctor["user_id"],
            "license_number": f"PHASE5-LIC-{suffix}",
            "specialization": "Internal Medicine",
            "experience_years": 12,
            "consultation_fee": "80.00",
        },
    )
    assert profile.status_code == 201, profile.text
    start = datetime.now(UTC).replace(microsecond=0) + timedelta(days=4)
    slot = client.post(
        "/api/v1/doctors/me/availability",
        headers={"Authorization": f"Bearer {doctor['access_token']}"},
        json={
            "start_time": start.isoformat(),
            "end_time": (start + timedelta(hours=1)).isoformat(),
        },
    )
    assert slot.status_code == 201, slot.text
    booking = client.post(
        "/api/v1/bookings",
        headers={"Authorization": f"Bearer {patient['access_token']}"},
        json={"slot_id": slot.json()["id"], "idempotency_key": f"phase5-booking-{suffix}"},
    )
    assert booking.status_code == 201, booking.text
    return doctor, patient, booking.json()


def test_consultation_lifecycle_authorization_and_idempotency(client):
    doctor, patient, booking = setup_consultation(client)
    patient_headers = {"Authorization": f"Bearer {patient['access_token']}"}
    doctor_headers = {"Authorization": f"Bearer {doctor['access_token']}"}
    payload = {
        "booking_id": booking["id"],
        "idempotency_key": "consultation-key-01",
        "clinical_notes": "Initial assessment",
    }

    created = client.post("/api/v1/consultations", headers=patient_headers, json=payload)
    replay = client.post("/api/v1/consultations", headers=patient_headers, json=payload)
    assert created.status_code == 201, created.text
    assert replay.status_code == 201
    assert replay.json()["id"] == created.json()["id"]
    consultation_id = created.json()["id"]

    started = client.patch(
        f"/api/v1/consultations/{consultation_id}/status",
        headers=doctor_headers,
        json={"status": "IN_PROGRESS"},
    )
    completed = client.patch(
        f"/api/v1/consultations/{consultation_id}/status",
        headers=doctor_headers,
        json={"status": "COMPLETED"},
    )
    assert started.status_code == 200
    assert completed.status_code == 200

    invalid = client.patch(
        f"/api/v1/consultations/{consultation_id}/status",
        headers=doctor_headers,
        json={"status": "IN_PROGRESS"},
    )
    assert invalid.status_code == 409


def test_prescription_creation_is_doctor_only_and_idempotent(client):
    doctor, patient, booking = setup_consultation(client, "02")
    patient_headers = {"Authorization": f"Bearer {patient['access_token']}"}
    doctor_headers = {"Authorization": f"Bearer {doctor['access_token']}"}
    consultation = client.post(
        "/api/v1/consultations",
        headers=patient_headers,
        json={
            "booking_id": booking["id"],
            "idempotency_key": "consultation-key-02",
        },
    ).json()
    started = client.patch(
        f"/api/v1/consultations/{consultation['id']}/status",
        headers=doctor_headers,
        json={"status": "IN_PROGRESS"},
    )
    assert started.status_code == 200
    prescription_payload = {
        "idempotency_key": "prescription-key-02",
        "medications": [
            {
                "name": "Amoxicillin",
                "dosage": "500 mg",
                "frequency": "Twice daily",
                "duration": "7 days",
            }
        ],
        "instructions": "Take after meals",
    }
    denied = client.post(
        f"/api/v1/prescriptions/consultations/{consultation['id']}",
        headers=patient_headers,
        json=prescription_payload,
    )
    created = client.post(
        f"/api/v1/prescriptions/consultations/{consultation['id']}",
        headers=doctor_headers,
        json=prescription_payload,
    )
    replay = client.post(
        f"/api/v1/prescriptions/consultations/{consultation['id']}",
        headers=doctor_headers,
        json=prescription_payload,
    )
    assert denied.status_code == 403
    assert created.status_code == 201, created.text
    assert replay.status_code == 201
    assert replay.json()["id"] == created.json()["id"]
    assert created.json()["medications"][0]["name"] == "Amoxicillin"

    fetched = client.get(f"/api/v1/prescriptions/{created.json()['id']}", headers=patient_headers)
    assert fetched.status_code == 200


def test_consultation_and_prescription_audit_outbox_events(client):
    doctor, patient, booking = setup_consultation(client, "03")
    patient_headers = {"Authorization": f"Bearer {patient['access_token']}"}
    doctor_headers = {"Authorization": f"Bearer {doctor['access_token']}"}
    consultation = client.post(
        "/api/v1/consultations",
        headers=patient_headers,
        json={
            "booking_id": booking["id"],
            "idempotency_key": "consultation-key-03",
        },
    ).json()
    client.patch(
        f"/api/v1/consultations/{consultation['id']}/status",
        headers=doctor_headers,
        json={"status": "IN_PROGRESS"},
    )
    client.post(
        f"/api/v1/prescriptions/consultations/{consultation['id']}",
        headers=doctor_headers,
        json={
            "idempotency_key": "prescription-key-03",
            "medications": [
                {
                    "name": "Vitamin D",
                    "dosage": "1000 IU",
                    "frequency": "Daily",
                    "duration": "30 days",
                }
            ],
        },
    )

    async def counts() -> tuple[int, int]:
        async with AsyncSessionLocal() as session:
            audit = await session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.event_type.in_(["consultation.created", "prescription.created"]))
            )
            outbox = await session.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.event_type.in_(["consultation.created", "prescription.created"]))
            )
            return int(audit or 0), int(outbox or 0)

    assert anyio.run(counts) == (2, 2)
