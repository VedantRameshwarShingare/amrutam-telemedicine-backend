"""Create consultations and prescriptions

Revision ID: 20260920_000004
Revises: 20260920_000003
Create Date: 2026-09-20 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260920_000004"
down_revision = "20260920_000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consultations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=False),
        sa.Column("doctor_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="SCHEDULED"),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("clinical_notes", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["doctor_id"], ["doctors.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["patient_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("booking_id", name="uq_consultations_booking_id"),
        sa.UniqueConstraint(
            "patient_id",
            "idempotency_key",
            name="uq_consultations_patient_idempotency",
        ),
    )
    op.create_index("ix_consultations_doctor_id", "consultations", ["doctor_id"])
    op.create_index("ix_consultations_patient_id", "consultations", ["patient_id"])
    op.create_index(
        "ix_consultations_doctor_status",
        "consultations",
        ["doctor_id", "status"],
    )
    op.create_index(
        "ix_consultations_patient_created",
        "consultations",
        ["patient_id", "created_at"],
    )

    op.create_table(
        "prescriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("consultation_id", sa.Uuid(), nullable=False),
        sa.Column("doctor_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("medications", sa.Text(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["consultation_id"], ["consultations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["doctor_id"], ["doctors.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["patient_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "consultation_id",
            "idempotency_key",
            name="uq_prescriptions_consultation_idempotency",
        ),
    )
    op.create_index("ix_prescriptions_consultation_id", "prescriptions", ["consultation_id"])
    op.create_index("ix_prescriptions_doctor_id", "prescriptions", ["doctor_id"])
    op.create_index("ix_prescriptions_patient_id", "prescriptions", ["patient_id"])
    op.create_index(
        "ix_prescriptions_patient_created",
        "prescriptions",
        ["patient_id", "created_at"],
    )
    op.create_index(
        "ix_prescriptions_doctor_created",
        "prescriptions",
        ["doctor_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_prescriptions_doctor_created", table_name="prescriptions")
    op.drop_index("ix_prescriptions_patient_created", table_name="prescriptions")
    op.drop_index("ix_prescriptions_patient_id", table_name="prescriptions")
    op.drop_index("ix_prescriptions_doctor_id", table_name="prescriptions")
    op.drop_index("ix_prescriptions_consultation_id", table_name="prescriptions")
    op.drop_table("prescriptions")
    op.drop_index("ix_consultations_patient_created", table_name="consultations")
    op.drop_index("ix_consultations_doctor_status", table_name="consultations")
    op.drop_index("ix_consultations_patient_id", table_name="consultations")
    op.drop_index("ix_consultations_doctor_id", table_name="consultations")
    op.drop_table("consultations")
