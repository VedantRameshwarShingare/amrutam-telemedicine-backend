from __future__ import annotations

import pytest
from app.core.security import (
    create_access_token,
    decode_token,
    hash_password,
    validate_password_policy,
    verify_password,
)
from app.modules.users.models import User, UserRole

pytestmark = pytest.mark.unit


def test_password_hash_round_trip_does_not_expose_plaintext():
    password = "StrongPass123!"
    password_hash = hash_password(password)

    assert password_hash != password
    assert verify_password(password, password_hash)
    assert not verify_password("WrongPass123!", password_hash)


@pytest.mark.parametrize(
    "password",
    ["short", "alllowercase1!", "ALLUPPERCASE1!", "NoDigits!", "NoSpecial123"],
)
def test_password_policy_rejects_weak_passwords(password: str):
    with pytest.raises(ValueError):
        validate_password_policy(password)


def test_access_token_round_trip_contains_only_identity_claims():
    user = User(email="unit@example.com", phone="+15550000001", role=UserRole.PATIENT)

    payload = decode_token(create_access_token(user))

    assert payload["sub"] == str(user.id)
    assert payload["role"] == "PATIENT"
    assert payload["type"] == "access"
    assert "password" not in payload