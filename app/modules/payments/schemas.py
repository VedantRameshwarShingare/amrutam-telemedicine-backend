from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.modules.payments.models import PaymentStatus
from pydantic import BaseModel, ConfigDict, Field, field_validator


class PaymentCreateRequest(BaseModel):
    booking_id: UUID
    idempotency_key: str = Field(min_length=8, max_length=128)
    currency: str = Field(default="INR", min_length=3, max_length=3)

    @field_validator("idempotency_key")
    @classmethod
    def normalize_idempotency_key(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Idempotency key cannot be blank")
        return value

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        value = value.strip().upper()
        if not value.isalpha():
            raise ValueError("Currency must contain only letters")
        return value


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    booking_id: UUID
    patient_id: UUID
    amount: Decimal
    currency: str
    status: PaymentStatus
    provider: str
    provider_payment_id: str | None
    idempotency_key: str
    failure_code: str | None
    failure_message: str | None
    version: int
    created_at: datetime
    updated_at: datetime
