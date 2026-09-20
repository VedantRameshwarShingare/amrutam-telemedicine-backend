"""Create payments

Revision ID: 20260920_000005
Revises: 20260920_000004
Create Date: 2026-09-20 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260920_000005"
down_revision = "20260920_000004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="INR"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("provider", sa.String(length=50), nullable=False, server_default="mock"),
        sa.Column("provider_payment_id", sa.String(length=255), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("failure_code", sa.String(length=100), nullable=True),
        sa.Column("failure_message", sa.String(length=500), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["patient_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("booking_id", name="uq_payments_booking_id"),
        sa.UniqueConstraint(
            "patient_id",
            "idempotency_key",
            name="uq_payments_patient_idempotency",
        ),
        sa.UniqueConstraint("provider_payment_id", name="uq_payments_provider_payment_id"),
    )
    op.create_index("ix_payments_patient_id", "payments", ["patient_id"])
    op.create_index("ix_payments_patient_created", "payments", ["patient_id", "created_at"])
    op.create_index("ix_payments_status_created", "payments", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_payments_status_created", table_name="payments")
    op.drop_index("ix_payments_patient_created", table_name="payments")
    op.drop_index("ix_payments_patient_id", table_name="payments")
    op.drop_table("payments")
