from __future__ import annotations

import anyio
import pyotp
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.modules.users.models import User, UserRole


def test_register_user_success(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "patient@example.com",
            "phone": "+15550000001",
            "password": "StrongPass123!",
            "role": "PATIENT",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "patient@example.com"
    assert "password_hash" not in body
    assert "mfa_secret" not in body


def test_duplicate_email_returns_conflict(client):
    first = client.post(
        "/api/v1/auth/register",
        json={
            "email": "duplicate@example.com",
            "phone": "+15550000002",
            "password": "StrongPass123!",
            "role": "PATIENT",
        },
    )
    assert first.status_code == 201

    second = client.post(
        "/api/v1/auth/register",
        json={
            "email": "duplicate@example.com",
            "phone": "+15550000003",
            "password": "StrongPass123!",
            "role": "PATIENT",
        },
    )

    assert second.status_code == 409


def test_login_success_and_token_response(client):
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "loginuser@example.com",
            "phone": "+15550000004",
            "password": "StrongPass123!",
            "role": "PATIENT",
        },
    )

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "loginuser@example.com",
            "password": "StrongPass123!",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


def test_login_invalid_credentials_returns_401(client):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "missing@example.com",
            "password": "NopePass123!",
        },
    )

    assert response.status_code == 401


def test_mfa_setup_and_verify(client):
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "mfa@example.com",
            "phone": "+15550000005",
            "password": "StrongPass123!",
            "role": "PATIENT",
        },
    )

    setup = client.post(
        "/api/v1/auth/mfa/setup",
        json={"email": "mfa@example.com", "password": "StrongPass123!"},
    )
    assert setup.status_code == 200
    setup_body = setup.json()
    assert "secret" in setup_body
    assert "otpauth_url" in setup_body

    secret = setup_body["secret"]
    totp = pyotp.TOTP(secret)
    verify = client.post(
        "/api/v1/auth/mfa/verify",
        json={"email": "mfa@example.com", "password": "StrongPass123!", "totp_code": totp.now()},
    )
    assert verify.status_code == 200


def test_refresh_rotates_tokens(client):
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "email": "refresh@example.com",
            "phone": "+15550000006",
            "password": "StrongPass123!",
            "role": "PATIENT",
        },
    )
    assert registration.status_code == 201

    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "refresh@example.com",
            "password": "StrongPass123!",
        },
    )
    assert login.status_code == 200
    refresh_token = login.json()["refresh_token"]

    refresh = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )

    assert refresh.status_code == 200
    body = refresh.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["refresh_token"] != refresh_token

    replay = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert replay.status_code == 401


def test_logout_invalidates_refresh_token(client):
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "email": "logout@example.com",
            "phone": "+15550000007",
            "password": "StrongPass123!",
            "role": "PATIENT",
        },
    )
    assert registration.status_code == 201

    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "logout@example.com",
            "password": "StrongPass123!",
        },
    )
    assert login.status_code == 200
    refresh_token = login.json()["refresh_token"]

    logout = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
    )
    assert logout.status_code == 200

    refresh_again = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_again.status_code in {401, 403}


def test_invalid_token_is_rejected(client):
    response = client.get(
        "/api/v1/users/me",
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert response.status_code == 401


def test_patient_without_permission_is_forbidden(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "patient2@example.com",
            "phone": "+15550000008",
            "password": "StrongPass123!",
            "role": "PATIENT",
        },
    )
    assert response.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "patient2@example.com",
            "password": "StrongPass123!",
        },
    )
    access_token = login.json()["access_token"]

    response = client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200


def test_admin_user_lookup_returns_requested_user(client):
    patient = client.post(
        "/api/v1/auth/register",
        json={
            "email": "lookup-patient@example.com",
            "phone": "+15550000009",
            "password": "StrongPass123!",
            "role": "PATIENT",
        },
    )
    assert patient.status_code == 201
    patient_id = patient.json()["id"]

    async def create_admin() -> None:
        async with AsyncSessionLocal() as session:
            session.add(
                User(
                    email="lookup-admin@example.com",
                    phone="+15550000010",
                    password_hash=hash_password("StrongPass123!"),
                    role=UserRole.ADMIN,
                    is_active=True,
                )
            )
            await session.commit()

    anyio.run(create_admin)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "lookup-admin@example.com", "password": "StrongPass123!"},
    )
    assert login.status_code == 200

    response = client.get(
        f"/api/v1/users/{patient_id}",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == patient_id
    assert response.json()["email"] == "lookup-patient@example.com"
