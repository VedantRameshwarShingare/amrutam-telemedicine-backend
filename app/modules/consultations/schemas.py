from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.modules.consultations.models import ConsultationStatus
from pydantic import BaseModel, ConfigDict, Field


class ConsultationCreateRequest(BaseModel):
    booking_id: UUID
    idempotency_key: str = Field(min_length=8, max_length=128)
    clinical_notes: str | None = Field(default=None, max_length=10000)


class ConsultationStatusRequest(BaseModel):
    status: ConsultationStatus
    clinical_notes: str | None = Field(default=None, max_length=10000)


class ConsultationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    booking_id: UUID
    doctor_id: UUID
    patient_id: UUID
    status: ConsultationStatus
    idempotency_key: str
    clinical_notes: str | None
    version: int
    created_at: datetime
    updated_at: datetime
