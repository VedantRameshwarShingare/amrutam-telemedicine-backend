from __future__ import annotations

import os

import pytest
from tests.test_bookings import register

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_INTEGRATION") == "1",
        reason="synchronous TestClient contract tests use the isolated test database",
    ),
]


def test_registration_validation_does_not_leak_credentials(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "contract@example.com",
            "phone": "+15550009999",
            "password": "weak",
            "role": "PATIENT",
        },
    )

    assert response.status_code == 422
    body = response.json()
    serialized = str(body).lower()
    assert "password_hash" not in serialized
    assert "jwt_secret" not in serialized
    assert "access_token" not in serialized


def test_patient_cannot_use_admin_or_doctor_mutation_endpoints(client):
    patient = register(client, "contract-patient@example.com", "+15550009998", "PATIENT")
    headers = {"Authorization": f"Bearer {patient['access_token']}"}

    admin_endpoint = client.get("/api/v1/auth/admin-example", headers=headers)
    doctor_endpoint = client.post(
        "/api/v1/doctors",
        headers=headers,
        json={
            "user_id": patient["user_id"],
            "license_number": "CONTRACT-LIC-01",
            "specialization": "General Medicine",
            "experience_years": 1,
            "consultation_fee": "25.00",
        },
    )

    assert admin_endpoint.status_code == 403
    assert doctor_endpoint.status_code == 403
