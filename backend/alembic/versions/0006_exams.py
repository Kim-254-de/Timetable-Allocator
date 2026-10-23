"""exams: course modes, exam papers, practicals, invigilators, and publications by kind

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-23 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("courses") as batch:
        batch.add_column(sa.Column("mode", sa.String(length=20), nullable=False, server_default="regular"))
    with op.batch_alter_table("department_publications") as batch:
        batch.add_column(sa.Column("kind", sa.String(length=20), nullable=False, server_default="teaching"))
    op.create_table(
        "exam_papers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("generator_term_id", sa.String(length=64), nullable=False),
        sa.Column("department_code", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("examiner_id", sa.Uuid(), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=False),
        sa.Column("published_signature", sa.String(length=64), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["examiner_id"], ["lecturers.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_exam_paper_department", "exam_papers", ["generator_term_id", "department_code"], unique=False
    )
    op.create_index("ix_exam_papers_examiner_id", "exam_papers", ["examiner_id"], unique=False)
    op.create_table(
        "exam_paper_units",
        sa.Column("paper_id", sa.Uuid(), nullable=False),
        sa.Column("unit_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["paper_id"], ["exam_papers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("paper_id", "unit_id"),
    )
    op.create_index("ix_exam_paper_units_unit_id", "exam_paper_units", ["unit_id"], unique=True)
    op.create_table(
        "no_written_exams",
        sa.Column("unit_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("unit_id"),
    )
    op.create_table(
        "practicals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("generator_term_id", sa.String(length=64), nullable=False),
        sa.Column("department_code", sa.String(length=32), nullable=False),
        sa.Column("unit_id", sa.Uuid(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_practical_department", "practicals", ["generator_term_id", "department_code"], unique=False)
    op.create_index("ix_practicals_unit_id", "practicals", ["unit_id"], unique=False)
    op.create_table(
        "invigilations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("paper_id", sa.Uuid(), nullable=False),
        sa.Column("room", sa.String(length=30), nullable=False),
        sa.Column("lecturer_id", sa.Uuid(), nullable=False),
        sa.Column("entered_by_name", sa.String(length=255), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["lecturer_id"], ["lecturers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["paper_id"], ["exam_papers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("paper_id", "room", name="uq_invigilation_paper_room"),
    )
    op.create_index("ix_invigilations_paper_id", "invigilations", ["paper_id"], unique=False)
    op.create_index("ix_invigilations_lecturer_id", "invigilations", ["lecturer_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_invigilations_lecturer_id", table_name="invigilations")
    op.drop_index("ix_invigilations_paper_id", table_name="invigilations")
    op.drop_table("invigilations")
    op.drop_index("ix_practicals_unit_id", table_name="practicals")
    op.drop_index("ix_practical_department", table_name="practicals")
    op.drop_table("practicals")
    op.drop_table("no_written_exams")
    op.drop_index("ix_exam_paper_units_unit_id", table_name="exam_paper_units")
    op.drop_table("exam_paper_units")
    op.drop_index("ix_exam_papers_examiner_id", table_name="exam_papers")
    op.drop_index("ix_exam_paper_department", table_name="exam_papers")
    op.drop_table("exam_papers")
    with op.batch_alter_table("department_publications") as batch:
        batch.drop_column("kind")
    with op.batch_alter_table("courses") as batch:
        batch.drop_column("mode")
