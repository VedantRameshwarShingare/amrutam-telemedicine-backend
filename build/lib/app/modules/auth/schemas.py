from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from app.core.security import validate_password_policy
from app.modules.users.models import UserRole
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserRegistrationRequest(BaseModel):
    email: EmailStr
    phone: str = Field(min_length=8, max_length=32)
    password: str = Field(min_length=8, max_length=128)
    role: UserRole | None = None

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str) -> str:
        return value.strip()

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        validate_password_policy(value)
        return value


class UserPublicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    phone: str
    role: UserRole
    mfa_enabled: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class MFATokenSetupRequest(BaseModel):
    email: EmailStr
    password: str


class MFASetupResponse(BaseModel):
    secret: str
    otpauth_url: str
    verified: bool = False


class MFAVerifyRequest(BaseModel):
    email: EmailStr
    password: str
    totp_code: str


class TokenPayload(BaseModel):
    sub: str
    role: str
    type: str
    iat: datetime
    exp: datetime
    jti: str


class ErrorResponse(BaseModel):
    error: dict[str, Any]
