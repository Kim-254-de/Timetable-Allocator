"""departments enter their teaching: courses, units, groups and publishing

The old allocation form's tables (form_entries, form_submissions) are left in
place, unused, so nothing entered on it is lost; a later migration drops them.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-23 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "courses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("generator_term_id", sa.String(length=64), nullable=False),
        sa.Column("department_code", sa.String(length=32), nullable=False),
        sa.Column("programme", sa.String(length=64), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("semester", sa.Integer(), nullable=False),
        sa.Column("sub_class", sa.String(length=10), nullable=False),
        sa.Column("students", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "generator_term_id", "programme", "year", "semester", "sub_class", name="uq_course_term_cohort"
        ),
    )
    op.create_index("ix_course_department", "courses", ["generator_term_id", "department_code"], unique=False)
    op.create_table(
        "units",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("generator_term_id", sa.String(length=64), nullable=False),
        sa.Column("department_code", sa.String(length=32), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("code_key", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("weekly_hours", sa.Integer(), nullable=False),
        sa.Column("class_length", sa.Integer(), nullable=False),
        sa.Column("room_type", sa.String(length=30), nullable=False),
        sa.Column("published_signature", sa.String(length=64), nullable=True),
        sa.Column("entered_by_name", sa.String(length=255), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("generator_term_id", "code_key", name="uq_unit_term_code"),
    )
    op.create_index("ix_unit_department", "units", ["generator_term_id", "department_code"], unique=False)
    op.create_table(
        "unit_courses",
        sa.Column("unit_id", sa.Uuid(), nullable=False),
        sa.Column("course_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("unit_id", "course_id"),
    )
    op.create_index("ix_unit_courses_course_id", "unit_courses", ["course_id"], unique=False)
    op.create_table(
        "unit_groups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("unit_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(length=50), nullable=False),
        sa.Column("lecturer_id", sa.Uuid(), nullable=True),
        sa.Column("lecture_hours", sa.Numeric(precision=6, scale=1), nullable=True),
        sa.Column("practical_hours", sa.Numeric(precision=6, scale=1), nullable=True),
        sa.Column("cf_hours", sa.Numeric(precision=6, scale=1), nullable=True),
        sa.ForeignKeyConstraint(["lecturer_id"], ["lecturers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("unit_id", "label", name="uq_unit_group_label"),
    )
    op.create_index("ix_unit_groups_unit_id", "unit_groups", ["unit_id"], unique=False)
    op.create_index("ix_unit_groups_lecturer_id", "unit_groups", ["lecturer_id"], unique=False)
    op.create_table(
        "unit_group_members",
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("course_id", sa.Uuid(), nullable=False),
        sa.Column("students", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["group_id"], ["unit_groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("group_id", "course_id"),
    )
    op.create_index("ix_unit_group_members_course_id", "unit_group_members", ["course_id"], unique=False)
    op.create_table(
        "department_publications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("generator_term_id", sa.String(length=64), nullable=False),
        sa.Column("department_code", sa.String(length=32), nullable=False),
        sa.Column("department_name", sa.String(length=255), nullable=False),
        sa.Column("published_by_account_id", sa.String(length=64), nullable=False),
        sa.Column("published_by_name", sa.String(length=255), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("unit_count", sa.Integer(), nullable=False),
        sa.Column("group_count", sa.Integer(), nullable=False),
        sa.Column("reopened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reopened_by_name", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_department_publication",
        "department_publications",
        ["generator_term_id", "department_code"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_department_publication", table_name="department_publications")
    op.drop_table("department_publications")
    op.drop_index("ix_unit_group_members_course_id", table_name="unit_group_members")
    op.drop_table("unit_group_members")
    op.drop_index("ix_unit_groups_lecturer_id", table_name="unit_groups")
    op.drop_index("ix_unit_groups_unit_id", table_name="unit_groups")
    op.drop_table("unit_groups")
    op.drop_index("ix_unit_courses_course_id", table_name="unit_courses")
    op.drop_table("unit_courses")
    op.drop_index("ix_unit_department", table_name="units")
    op.drop_table("units")
    op.drop_index("ix_course_department", table_name="courses")
    op.drop_table("courses")
