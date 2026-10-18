"""remember each allocated class's meetings, to flag later timetable changes

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-18 22:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("allocations", sa.Column("meetings_at_allocation", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("allocations", "meetings_at_allocation")
