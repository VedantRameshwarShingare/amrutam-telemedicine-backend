from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.modules.doctors.models import DoctorStatus, SlotStatus
from pydantic import BaseModel, ConfigDict, Field, field_validator


class DoctorCreateRequest(BaseModel):
    user_id: UUID
    license_number: str = Field(min_length=2, max_length=100)
    specialization: str = Field(min_length=2, max_length=120)
    experience_years: int = Field(ge=0, le=80)
    consultation_fee: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    status: DoctorStatus = DoctorStatus.ACTIVE

    @field_validator("license_number", "specialization")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()


class DoctorUpdateRequest(BaseModel):
    specialization: str | None = Field(default=None, min_length=2, max_length=120)
    experience_years: int | None = Field(default=None, ge=0, le=80)
    consultation_fee: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    status: DoctorStatus | None = None

    @field_validator("specialization")
    @classmethod
    def normalize_specialization(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class DoctorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    license_number: str
    specialization: str
    experience_years: int
    consultation_fee: Decimal
    status: DoctorStatus
    created_at: datetime
    updated_at: datetime


class DoctorListResponse(BaseModel):
    items: list[DoctorResponse]
    total: int
    page: int
    page_size: int


class AvailabilitySlotCreateRequest(BaseModel):
    start_time: datetime
    end_time: datetime


class AvailabilitySlotUpdateRequest(BaseModel):
    start_time: datetime | None = None
    end_time: datetime | None = None
    status: SlotStatus | None = None


class AvailabilitySlotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    doctor_id: UUID
    start_time: datetime
    end_time: datetime
    status: SlotStatus
    version: int
    created_at: datetime
    updated_at: datetime
