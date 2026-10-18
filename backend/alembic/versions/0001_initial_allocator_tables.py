"""initial allocator tables

Revision ID: 0001
Revises:
Create Date: 2026-10-18 20:18:38.392559
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_account_id", sa.String(length=64), nullable=False),
        sa.Column("actor_name", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("entity", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=False),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_entity", "audit_log", ["entity", "entity_id"], unique=False)
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_token", sa.String(length=64), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("identity", sa.JSON(), nullable=False),
        sa.Column("identity_checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_auth_sessions_account_id"), "auth_sessions", ["account_id"], unique=False)
    op.create_table(
        "login_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_login_attempt_key_at", "login_attempts", ["key", "at"], unique=False)
    op.create_table(
        "terms",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("smarttt_term_id", sa.String(length=64), nullable=False),
        sa.Column("academic_year", sa.String(length=20), nullable=False),
        sa.Column("semester", sa.Integer(), nullable=False),
        sa.Column("published_version_seen", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("smarttt_term_id"),
    )
    op.create_table(
        "allocations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("term_id", sa.Uuid(), nullable=False),
        sa.Column("section_key", sa.String(length=64), nullable=False),
        sa.Column("section_code", sa.String(length=100), nullable=False),
        sa.Column("group_label", sa.String(length=50), nullable=True),
        sa.Column("smarttt_unit_id", sa.Integer(), nullable=False),
        sa.Column("smarttt_department_id", sa.Integer(), nullable=False),
        sa.Column("smarttt_lecturer_id", sa.String(length=64), nullable=True),
        sa.Column("lecturer_name", sa.String(length=255), nullable=True),
        sa.Column("employment_type", sa.String(length=20), nullable=True),
        sa.Column("lecture_hours", sa.Numeric(precision=6, scale=1), nullable=True),
        sa.Column("practical_hours", sa.Numeric(precision=6, scale=1), nullable=True),
        sa.Column("cf_hours", sa.Numeric(precision=6, scale=1), nullable=True),
        sa.Column("entered_by_account_id", sa.String(length=64), nullable=False),
        sa.Column("entered_by_name", sa.String(length=255), nullable=False),
        sa.Column("entered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("synced_to_smarttt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Enum("saved", "submitted", name="allocation_status"), nullable=False),
        sa.ForeignKeyConstraint(["term_id"], ["terms.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("term_id", "section_key", name="uq_allocation_term_section"),
    )
    op.create_index(
        "ix_allocation_department", "allocations", ["term_id", "smarttt_department_id"], unique=False
    )
    op.create_table(
        "lecturer_availability",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("term_id", sa.Uuid(), nullable=False),
        sa.Column("smarttt_lecturer_id", sa.String(length=64), nullable=False),
        sa.Column("day", sa.String(length=3), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("created_by_account_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["term_id"], ["terms.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_availability_lecturer", "lecturer_availability", ["term_id", "smarttt_lecturer_id"], unique=False
    )
    op.create_table(
        "submissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("term_id", sa.Uuid(), nullable=False),
        sa.Column("department_id", sa.Integer(), nullable=False),
        sa.Column("submitted_by_account_id", sa.String(length=64), nullable=False),
        sa.Column("submitted_by_name", sa.String(length=255), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("section_count", sa.Integer(), nullable=False),
        sa.Column("allocated_count", sa.Integer(), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["term_id"], ["terms.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_submission_department", "submissions", ["term_id", "department_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_submission_department", table_name="submissions")
    op.drop_table("submissions")
    op.drop_index("ix_availability_lecturer", table_name="lecturer_availability")
    op.drop_table("lecturer_availability")
    op.drop_index("ix_allocation_department", table_name="allocations")
    op.drop_table("allocations")
    op.drop_table("terms")
    op.drop_index("ix_login_attempt_key_at", table_name="login_attempts")
    op.drop_table("login_attempts")
    op.drop_index(op.f("ix_auth_sessions_account_id"), table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_index("ix_audit_entity", table_name="audit_log")
    op.drop_table("audit_log")
    sa.Enum(name="allocation_status").drop(op.get_bind(), checkfirst=True)
