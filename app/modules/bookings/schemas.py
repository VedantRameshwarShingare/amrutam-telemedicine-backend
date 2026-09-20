from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.modules.bookings.models import BookingStatus
from pydantic import BaseModel, ConfigDict, Field


class BookingCreateRequest(BaseModel):
    slot_id: UUID
    idempotency_key: str = Field(min_length=8, max_length=128)


class BookingCancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class BookingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slot_id: UUID
    doctor_id: UUID
    patient_id: UUID
    status: BookingStatus
    idempotency_key: str
    cancellation_reason: str | None
    version: int
    created_at: datetime
    updated_at: datetime


class BookingListResponse(BaseModel):
    items: list[BookingResponse]
    total: int
    page: int
    page_size: int
