from __future__ import annotations

import json
from datetime import datetime
from typing import cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MedicationItem(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    dosage: str = Field(min_length=1, max_length=100)
    frequency: str = Field(min_length=1, max_length=100)
    duration: str = Field(min_length=1, max_length=100)
    instructions: str | None = Field(default=None, max_length=500)


class PrescriptionCreateRequest(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=128)
    medications: list[MedicationItem] = Field(min_length=1, max_length=50)
    instructions: str | None = Field(default=None, max_length=5000)


class PrescriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    consultation_id: UUID
    doctor_id: UUID
    patient_id: UUID
    idempotency_key: str
    medications: list[MedicationItem]
    instructions: str | None
    created_at: datetime
    updated_at: datetime

    @field_validator("medications", mode="before")
    @classmethod
    def decode_medications(cls, value: str | list[dict[str, str]]) -> list[dict[str, str]]:
        if isinstance(value, str):
            return cast(list[dict[str, str]], json.loads(value))
        return value
