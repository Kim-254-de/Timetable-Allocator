"""the allocation form sends its lecturers to SMARTTT: what each class last sent

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-19 23:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("form_entries", sa.Column("smarttt_key", sa.String(length=80), nullable=True))
    op.add_column("form_entries", sa.Column("smarttt_lecturer_id", sa.String(length=64), nullable=True))
    op.add_column("form_entries", sa.Column("smarttt_sent_for", sa.String(length=64), nullable=True))
    op.add_column("form_entries", sa.Column("smarttt_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("form_entries", sa.Column("smarttt_error", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("form_entries", "smarttt_error")
    op.drop_column("form_entries", "smarttt_synced_at")
    op.drop_column("form_entries", "smarttt_sent_for")
    op.drop_column("form_entries", "smarttt_lecturer_id")
    op.drop_column("form_entries", "smarttt_key")
