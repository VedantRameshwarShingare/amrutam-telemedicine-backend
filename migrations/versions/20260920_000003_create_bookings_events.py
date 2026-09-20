"""Create bookings, audit events, and outbox events

Revision ID: 20260920_000003
Revises: 20260919_000002
Create Date: 2026-09-20 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260920_000003"
down_revision = "20260919_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bookings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slot_id", sa.Uuid(), nullable=False),
        sa.Column("doctor_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="CONFIRMED"),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("cancellation_reason", sa.String(length=500), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["doctor_id"], ["doctors.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["patient_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["slot_id"], ["availability_slots.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slot_id", name="uq_bookings_slot_id"),
        sa.UniqueConstraint(
            "patient_id",
            "idempotency_key",
            name="uq_bookings_patient_idempotency",
        ),
    )
    op.create_index("ix_bookings_patient_id", "bookings", ["patient_id"])
    op.create_index("ix_bookings_doctor_id", "bookings", ["doctor_id"])
    op.create_index(
        "ix_bookings_patient_created",
        "bookings",
        ["patient_id", "created_at"],
    )
    op.create_index(
        "ix_bookings_doctor_created",
        "bookings",
        ["doctor_id", "created_at"],
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])
    op.create_index("ix_audit_events_entity_id", "audit_events", ["entity_id"])

    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("aggregate_type", sa.String(length=100), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_outbox_events_event_type", "outbox_events", ["event_type"])
    op.create_index("ix_outbox_events_aggregate_id", "outbox_events", ["aggregate_id"])


def downgrade() -> None:
    op.drop_index("ix_outbox_events_aggregate_id", table_name="outbox_events")
    op.drop_index("ix_outbox_events_event_type", table_name="outbox_events")
    op.drop_table("outbox_events")
    op.drop_index("ix_audit_events_entity_id", table_name="audit_events")
    op.drop_index("ix_audit_events_event_type", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_bookings_doctor_created", table_name="bookings")
    op.drop_index("ix_bookings_patient_created", table_name="bookings")
    op.drop_index("ix_bookings_doctor_id", table_name="bookings")
    op.drop_index("ix_bookings_patient_id", table_name="bookings")
    op.drop_table("bookings")
