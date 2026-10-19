"""the allocation form: department lecturers, form rows and submissions

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-19 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

employment_type = sa.Enum("full_time", "part_time", name="employment_type")


def upgrade() -> None:
    op.create_table(
        "lecturers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("department_code", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=30), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("staff_number", sa.String(length=64), nullable=True),
        sa.Column("employment_type", employment_type, nullable=False),
        sa.Column("phone", sa.String(length=40), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("max_weekly_hours", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lecturer_department", "lecturers", ["department_code"], unique=False)
    op.create_table(
        "form_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("generator_term_id", sa.String(length=64), nullable=False),
        sa.Column("department_code", sa.String(length=32), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("unit_code", sa.String(length=64), nullable=False),
        sa.Column("unit_title", sa.String(length=255), nullable=False),
        sa.Column("group_label", sa.String(length=50), nullable=False),
        sa.Column("class_rows", sa.JSON(), nullable=False),
        sa.Column("lecturer_id", sa.Uuid(), nullable=True),
        sa.Column("lecture_hours", sa.Numeric(precision=6, scale=1), nullable=True),
        sa.Column("practical_hours", sa.Numeric(precision=6, scale=1), nullable=True),
        sa.Column("cf_hours", sa.Numeric(precision=6, scale=1), nullable=True),
        sa.Column("entered_by_account_id", sa.String(length=64), nullable=False),
        sa.Column("entered_by_name", sa.String(length=255), nullable=False),
        sa.Column("entered_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["lecturer_id"], ["lecturers.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("generator_term_id", "key", name="uq_form_entry_term_key"),
    )
    op.create_index(
        "ix_form_entry_department", "form_entries", ["generator_term_id", "department_code"], unique=False
    )
    op.create_table(
        "form_submissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("generator_term_id", sa.String(length=64), nullable=False),
        sa.Column("department_code", sa.String(length=32), nullable=False),
        sa.Column("submitted_by_account_id", sa.String(length=64), nullable=False),
        sa.Column("submitted_by_name", sa.String(length=255), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entry_count", sa.Integer(), nullable=False),
        sa.Column("allocated_count", sa.Integer(), nullable=False),
        sa.Column("reopened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reopened_by_name", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_form_submission_department", "form_submissions", ["generator_term_id", "department_code"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_form_submission_department", table_name="form_submissions")
    op.drop_table("form_submissions")
    op.drop_index("ix_form_entry_department", table_name="form_entries")
    op.drop_table("form_entries")
    op.drop_index("ix_lecturer_department", table_name="lecturers")
    op.drop_table("lecturers")
    employment_type.drop(op.get_bind(), checkfirst=True)
