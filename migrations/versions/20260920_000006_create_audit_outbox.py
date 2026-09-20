"""Compatibility revision for audit and outbox tables

Revision ID: 20260920_000006
Revises: 20260920_000005
Create Date: 2026-09-20 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260920_000006"
down_revision = "20260920_000005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Revision 000003 already creates these tables. Keep this revision in the
    # chain for databases that recorded the originally published revision.
    pass


def downgrade() -> None:
    pass