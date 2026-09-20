from __future__ import annotations

from datetime import UTC, datetime, timedelta

import anyio
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.modules.users.models import User, UserRole


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
    me = client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me.status_code == 200
    tokens["user_id"] = me.json()["id"]
    return tokens


def create_admin() -> User:
    async def create() -> User:
        async with AsyncSessionLocal() as session:
            admin = User(
                email="admin@example.com",
                phone="+15559990000",
                password_hash=hash_password("StrongPass123!"),
                role=UserRole.ADMIN,
                mfa_enabled=False,
                is_active=True,
            )
            session.add(admin)
            await session.commit()
            await session.refresh(admin)
            return admin

    return anyio.run(create)


def create_doctor_profile(client, admin_token: str, doctor_user_id: str) -> dict:
    response = client.post(
        "/api/v1/doctors",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "user_id": doctor_user_id,
            "license_number": f"LIC-{doctor_user_id[:8]}",
            "specialization": "Cardiology",
            "experience_years": 10,
            "consultation_fee": "75.00",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_admin_creates_and_patient_retrieves_doctor(client):
    doctor_login = register(client, "doctor@example.com", "+15550001001", "DOCTOR")
    admin = create_admin()
    admin_login = client.post(
        "/api/v1/auth/login",
        json={"email": admin.email, "password": "StrongPass123!"},
    )
    doctor = create_doctor_profile(
        client, admin_login.json()["access_token"], doctor_login["user_id"]
    )

    patient_login = register(client, "patient@example.com", "+15550001002", "PATIENT")
    response = client.get(
        f"/api/v1/doctors/{doctor['id']}",
        headers={"Authorization": f"Bearer {patient_login['access_token']}"},
    )

    assert response.status_code == 200
    assert response.json()["specialization"] == "Cardiology"


def test_doctor_filtering_and_pagination(client):
    doctor_login = register(client, "doctor2@example.com", "+15550001003", "DOCTOR")
    admin = create_admin()
    admin_login = client.post(
        "/api/v1/auth/login",
        json={"email": admin.email, "password": "StrongPass123!"},
    )
    create_doctor_profile(client, admin_login.json()["access_token"], doctor_login["user_id"])
    patient = register(client, "patient2@example.com", "+15550001004", "PATIENT")

    response = client.get(
        "/api/v1/doctors",
        params={"specialization": "cardiology", "experience_min": 5, "page": 1, "page_size": 1},
        headers={"Authorization": f"Bearer {patient['access_token']}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["page"] == 1


def test_doctor_availability_lifecycle_and_invalid_ranges(client):
    doctor_login = register(client, "doctor3@example.com", "+15550001005", "DOCTOR")
    admin = create_admin()
    admin_login = client.post(
        "/api/v1/auth/login",
        json={"email": admin.email, "password": "StrongPass123!"},
    )
    doctor = create_doctor_profile(
        client, admin_login.json()["access_token"], doctor_login["user_id"]
    )
    token = {"Authorization": f"Bearer {doctor_login['access_token']}"}
    start = datetime.now(UTC).replace(microsecond=0) + timedelta(days=1)

    invalid = client.post(
        "/api/v1/doctors/me/availability",
        headers=token,
        json={
            "start_time": (start + timedelta(hours=1)).isoformat(),
            "end_time": start.isoformat(),
        },
    )
    assert invalid.status_code == 422

    created = client.post(
        "/api/v1/doctors/me/availability",
        headers=token,
        json={
            "start_time": start.isoformat(),
            "end_time": (start + timedelta(hours=1)).isoformat(),
        },
    )
    assert created.status_code == 201, created.text
    slot = created.json()

    overlap = client.post(
        "/api/v1/doctors/me/availability",
        headers=token,
        json={
            "start_time": (start + timedelta(minutes=30)).isoformat(),
            "end_time": (start + timedelta(hours=2)).isoformat(),
        },
    )
    assert overlap.status_code == 409

    updated = client.patch(
        f"/api/v1/doctors/me/availability/{slot['id']}",
        headers=token,
        json={"status": "CANCELLED"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == 2

    deleted = client.delete(f"/api/v1/doctors/me/availability/{slot['id']}", headers=token)
    assert deleted.status_code == 204
    public = client.get(
        f"/api/v1/doctors/{doctor['id']}/availability",
        headers=token,
    )
    assert public.status_code == 200
    assert public.json()[0]["status"] == "CANCELLED"


def test_doctor_ownership_and_admin_authorization(client):
    first_login = register(client, "doctor4@example.com", "+15550001006", "DOCTOR")
    second_login = register(client, "doctor5@example.com", "+15550001007", "DOCTOR")
    admin = create_admin()
    admin_login = client.post(
        "/api/v1/auth/login",
        json={"email": admin.email, "password": "StrongPass123!"},
    )
    first = create_doctor_profile(
        client, admin_login.json()["access_token"], first_login["user_id"]
    )
    create_doctor_profile(client, admin_login.json()["access_token"], second_login["user_id"])
    start = datetime.now(UTC).replace(microsecond=0) + timedelta(days=2)
    own_slot = client.post(
        "/api/v1/doctors/me/availability",
        headers={"Authorization": f"Bearer {first_login['access_token']}"},
        json={
            "start_time": start.isoformat(),
            "end_time": (start + timedelta(hours=1)).isoformat(),
        },
    ).json()

    other_update = client.patch(
        f"/api/v1/doctors/me/availability/{own_slot['id']}",
        headers={"Authorization": f"Bearer {second_login['access_token']}"},
        json={"status": "CANCELLED"},
    )
    assert other_update.status_code == 404

    patient = register(client, "patient3@example.com", "+15550001008", "PATIENT")
    patient_create = client.post(
        "/api/v1/doctors/me/availability",
        headers={"Authorization": f"Bearer {patient['access_token']}"},
        json={
            "start_time": start.isoformat(),
            "end_time": (start + timedelta(hours=1)).isoformat(),
        },
    )
    assert patient_create.status_code == 403

    admin_update = client.patch(
        f"/api/v1/doctors/{first['id']}",
        headers={"Authorization": f"Bearer {admin_login.json()['access_token']}"},
        json={"status": "SUSPENDED"},
    )
    assert admin_update.status_code == 200
    assert admin_update.json()["status"] == "SUSPENDED"
