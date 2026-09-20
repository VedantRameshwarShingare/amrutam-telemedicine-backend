from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from app.core.base import Base
from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class PaymentStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("booking_id", name="uq_payments_booking_id"),
        UniqueConstraint("patient_id", "idempotency_key", name="uq_payments_patient_idempotency"),
        Index("ix_payments_patient_created", "patient_id", "created_at"),
        Index("ix_payments_status_created", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    booking_id: Mapped[UUID] = mapped_column(
        ForeignKey("bookings.id", ondelete="RESTRICT"), nullable=False
    )
    patient_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    status: Mapped[PaymentStatus] = mapped_column(
        String(32), nullable=False, default=PaymentStatus.PENDING
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="mock")
    provider_payment_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
