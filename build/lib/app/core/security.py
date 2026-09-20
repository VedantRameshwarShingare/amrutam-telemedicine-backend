from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID, uuid4

import jwt
import pyotp
from app.common.exceptions import AuthenticationError, AuthorizationError, RateLimitExceededError
from app.core.config import settings
from app.core.database import get_db
from app.core.redis import redis_client
from app.modules.users.models import User, UserRole
from argon2 import PasswordHasher
from fastapi import Depends, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

ph = PasswordHasher()
security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return ph.verify(password_hash, password)
    except Exception:
        return False


def create_access_token(user: User) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user.id),
        "role": str(user.role),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_access_token_expire_minutes)).timestamp()),
        "jti": str(uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user: User, *, token_family: str | None = None) -> str:
    now = datetime.now(UTC)
    token_family = token_family or secrets.token_urlsafe(32)
    payload = {
        "sub": str(user.id),
        "role": str(user.role),
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=settings.jwt_refresh_token_expire_days)).timestamp()),
        "jti": str(uuid4()),
        "tf": token_family,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


def validate_password_policy(password: str) -> None:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")
    if password.lower() == password:
        raise ValueError("Password must contain at least one uppercase character")
    if password.upper() == password:
        raise ValueError("Password must contain at least one lowercase character")
    if not any(char.isdigit() for char in password):
        raise ValueError("Password must contain at least one digit")
    if not any(char in "!@#$%^&*()_+-=[]{}|;:,.<>?" for char in password):
        raise ValueError("Password must contain at least one special character")


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def generate_totp_uri(email: str, secret: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=settings.mfa_issuer)


def verify_totp(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code, valid_window=1)


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Missing bearer token")

    token = credentials.credentials
    try:
        payload = decode_token(token)
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid token") from exc

    if payload.get("type") != "access":
        raise AuthenticationError("Token type is invalid for this endpoint")

    user_id = payload.get("sub")
    if not user_id:
        raise AuthenticationError("Token is missing user identity")

    try:
        user_uuid = UUID(str(user_id))
    except ValueError as exc:
        raise AuthenticationError("Token is missing valid user identity") from exc

    user = await db.get(User, user_uuid)
    if user is None or not user.is_active:
        raise AuthenticationError("User account is inactive")

    request.state.user = user
    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not current_user.is_active:
        raise AuthenticationError("User account is inactive")
    return current_user


def require_role(*roles: UserRole):
    async def dependency(
        current_user: Annotated[User, Depends(get_current_active_user)],
    ) -> User:
        if current_user.role not in roles:
            raise AuthorizationError("Insufficient permissions")
        return current_user

    return dependency


def require_roles(*roles: UserRole):
    return require_role(*roles)


async def can_access_user(current_user: User, target_user_id: str | None) -> bool:
    if current_user.role == UserRole.ADMIN:
        return True
    return current_user.id.hex == target_user_id if target_user_id else False


async def can_access_patient_data(current_user: User, patient_id: str | None) -> bool:
    if current_user.role == UserRole.ADMIN:
        return True
    if current_user.role == UserRole.PATIENT:
        return current_user.id.hex == patient_id if patient_id else False
    return False


async def can_access_doctor_data(current_user: User, doctor_id: str | None) -> bool:
    if current_user.role == UserRole.ADMIN:
        return True
    if current_user.role == UserRole.DOCTOR:
        return current_user.id.hex == doctor_id if doctor_id else False
    return False


async def rate_limit_login(email: str, ip: str) -> None:
    await _enforce_rate_limit(
        key=f"login:{email}:{ip}",
        limit=settings.login_rate_limit,
        window_seconds=settings.login_rate_limit_seconds,
        message="Too many login attempts",
    )


async def rate_limit_registration(ip: str) -> None:
    await _enforce_rate_limit(
        key=f"register:{ip}",
        limit=settings.registration_rate_limit,
        window_seconds=settings.registration_rate_limit_seconds,
        message="Too many registration attempts",
    )


async def rate_limit_refresh(user_id: str, ip: str) -> None:
    await _enforce_rate_limit(
        key=f"refresh:{user_id}:{ip}",
        limit=settings.refresh_rate_limit,
        window_seconds=settings.refresh_rate_limit_seconds,
        message="Too many refresh attempts",
    )


async def rate_limit_mfa(user_id: str) -> None:
    await _enforce_rate_limit(
        key=f"mfa:{user_id}",
        limit=settings.mfa_rate_limit,
        window_seconds=settings.mfa_rate_limit_seconds,
        message="Too many MFA attempts",
    )


async def _enforce_rate_limit(
    *,
    key: str,
    limit: int,
    window_seconds: int,
    message: str,
) -> None:
    try:
        count = await redis_client.incr(key)
        if count == 1:
            await redis_client.expire(key, window_seconds)
        if count > limit:
            raise RateLimitExceededError(message)
    except RateLimitExceededError:
        raise
    except Exception:
        return
