"""Create doctors and availability slots

Revision ID: 20260919_000002
Revises: 20260919_000001
Create Date: 2026-09-19 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260919_000002"
down_revision = "20260919_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "doctors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("license_number", sa.String(length=100), nullable=False),
        sa.Column("specialization", sa.String(length=120), nullable=False),
        sa.Column("experience_years", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consultation_fee", sa.Numeric(10, 2), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_doctors_user_id"),
        sa.UniqueConstraint("license_number", name="uq_doctors_license_number"),
    )
    op.create_index("ix_doctors_user_id", "doctors", ["user_id"], unique=True)
    op.create_index("ix_doctors_specialization", "doctors", ["specialization"])

    op.create_table(
        "availability_slots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("doctor_id", sa.Uuid(), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="AVAILABLE"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("start_time < end_time", name="ck_availability_slots_valid_time"),
        sa.ForeignKeyConstraint(["doctor_id"], ["doctors.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_availability_slots_doctor_start",
        "availability_slots",
        ["doctor_id", "start_time"],
    )

    # PostgreSQL enforces non-overlap atomically; application validation provides the SQLite path.
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
        op.execute(
            """
            ALTER TABLE availability_slots
            ADD CONSTRAINT ex_availability_slots_doctor_time
            EXCLUDE USING gist (
                doctor_id WITH =,
                tstzrange(start_time, end_time, '[)') WITH &&
            )
            WHERE (status IN ('AVAILABLE', 'HELD', 'BOOKED'))
            """
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE availability_slots "
            "DROP CONSTRAINT IF EXISTS ex_availability_slots_doctor_time"
        )
    op.drop_index("ix_availability_slots_doctor_start", table_name="availability_slots")
    op.drop_table("availability_slots")
    op.drop_index("ix_doctors_specialization", table_name="doctors")
    op.drop_index("ix_doctors_user_id", table_name="doctors")
    op.drop_table("doctors")
