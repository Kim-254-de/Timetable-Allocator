"""
The Allocator's own data.

What departments enter for a term of the Timetable Generator: their own list
of lecturers, their courses (cohorts), their units with the courses that take
them, and each unit's groups with a lecturer and the form's L/P/CF hours; and
each COD's publishing of it to the Director. The Generator imports what is
published and gives every group its day, time and room.

Also kept from the SMARTTT-based allocation: who allocated each SMARTTT class
and when, lecturers' unavailability, departments' submissions, the audit
trail, and sign-in sessions.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class AllocationStatus(enum.StrEnum):
    SAVED = "saved"  # sent to SMARTTT, department not yet submitted
    SUBMITTED = "submitted"  # part of the department's submitted allocation


class Term(Base):
    __tablename__ = "terms"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    smarttt_term_id: Mapped[str] = mapped_column(String(64), unique=True)
    academic_year: Mapped[str] = mapped_column(String(20))
    semester: Mapped[int] = mapped_column(Integer)
    published_version_seen: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Allocation(Base):
    """
    The latest allocation of one section (unit + group) in a term, as entered
    in the Allocator. SMARTTT holds the lecturer itself; this row records who
    set it, when it reached SMARTTT, and the allocation-form hours.
    """

    __tablename__ = "allocations"
    __table_args__ = (
        UniqueConstraint("term_id", "section_key", name="uq_allocation_term_section"),
        Index("ix_allocation_department", "term_id", "smarttt_department_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    term_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("terms.id", ondelete="RESTRICT"))
    section_key: Mapped[str] = mapped_column(String(64))
    section_code: Mapped[str] = mapped_column(String(100))
    group_label: Mapped[str | None] = mapped_column(String(50), nullable=True)
    smarttt_unit_id: Mapped[int] = mapped_column(Integer)
    smarttt_department_id: Mapped[int] = mapped_column(Integer)
    # None = the department cleared the lecturer.
    smarttt_lecturer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lecturer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    employment_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Semester hours as written on the department's allocation form (L, P, CF).
    lecture_hours: Mapped[Decimal | None] = mapped_column(Numeric(6, 1), nullable=True)
    practical_hours: Mapped[Decimal | None] = mapped_column(Numeric(6, 1), nullable=True)
    cf_hours: Mapped[Decimal | None] = mapped_column(Numeric(6, 1), nullable=True)
    entered_by_account_id: Mapped[str] = mapped_column(String(64))
    entered_by_name: Mapped[str] = mapped_column(String(255))
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    synced_to_smarttt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[AllocationStatus] = mapped_column(
        Enum(AllocationStatus, name="allocation_status", values_callable=lambda e: [m.value for m in e]),
        default=AllocationStatus.SAVED,
    )
    # The class's meetings (day, start, end, room) when the lecturer was given
    # it, so a later timetable version that moves the class is flagged.
    meetings_at_allocation: Mapped[list[dict[str, str]] | None] = mapped_column(JSON, nullable=True)

    term: Mapped[Term] = relationship()


class LecturerAvailability(Base):
    """A period in the teaching week when a lecturer cannot be given classes this term."""

    __tablename__ = "lecturer_availability"
    __table_args__ = (Index("ix_availability_lecturer", "term_id", "smarttt_lecturer_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    term_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("terms.id", ondelete="RESTRICT"))
    smarttt_lecturer_id: Mapped[str] = mapped_column(String(64))
    day: Mapped[str] = mapped_column(String(3))
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    reason: Mapped[str] = mapped_column(String(255), default="")
    created_by_account_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Submission(Base):
    """
    A COD submitting their department's allocation for a term. Changing an
    allocation afterwards supersedes the submission until the COD submits again.
    """

    __tablename__ = "submissions"
    __table_args__ = (Index("ix_submission_department", "term_id", "department_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    term_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("terms.id", ondelete="RESTRICT"))
    department_id: Mapped[int] = mapped_column(Integer)
    submitted_by_account_id: Mapped[str] = mapped_column(String(64))
    submitted_by_name: Mapped[str] = mapped_column(String(255))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    section_count: Mapped[int] = mapped_column(Integer)
    allocated_count: Mapped[int] = mapped_column(Integer)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_entity", "entity", "entity_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    actor_account_id: Mapped[str] = mapped_column(String(64))
    actor_name: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(64))
    entity: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(128))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuthSession(Base):
    """A signed-in browser. The cookie holds a random token; only its SHA-256 is stored."""

    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    account_id: Mapped[str] = mapped_column(String(64), index=True)
    identity: Mapped[dict[str, Any]] = mapped_column(JSON)
    identity_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user_agent: Mapped[str] = mapped_column(Text, default="")


class LoginAttempt(Base):
    """Failed sign-ins, for rate limiting by identifier and by client address."""

    __tablename__ = "login_attempts"
    __table_args__ = (Index("ix_login_attempt_key_at", "key", "at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(255))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# -- what departments enter ---------------------------------------------------------------


class EmploymentType(enum.StrEnum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"


class Lecturer(Base):
    """
    A lecturer on a department's own list. Departments enter their lecturers
    here; a lecturer teaching for two departments can be on both lists with the
    same staff number, and the clash check treats them as one person.
    """

    __tablename__ = "lecturers"
    __table_args__ = (Index("ix_lecturer_department", "department_code"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    department_code: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(30), default="")
    full_name: Mapped[str] = mapped_column(String(255))
    staff_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    employment_type: Mapped[EmploymentType] = mapped_column(
        Enum(EmploymentType, name="employment_type", values_callable=lambda e: [m.value for m in e]),
        default=EmploymentType.FULL_TIME,
    )
    phone: Mapped[str] = mapped_column(String(40), default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    max_weekly_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Course(Base):
    """
    A cohort a department teaches this term: programme + year + study semester
    (+ sub-class), e.g. "BSC.CS Y1S1, 120 students". It becomes a class row in
    the Generator. Every department can read every course (to pick another
    department's students for a unit it services), but edits only its own.
    A cohort is entered once per term, by the department it belongs to.
    """

    __tablename__ = "courses"
    __table_args__ = (
        UniqueConstraint(
            "generator_term_id", "programme", "year", "semester", "sub_class", name="uq_course_term_cohort"
        ),
        Index("ix_course_department", "generator_term_id", "department_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    generator_term_id: Mapped[str] = mapped_column(String(64))
    department_code: Mapped[str] = mapped_column(String(32))
    programme: Mapped[str] = mapped_column(String(64))
    year: Mapped[int] = mapped_column(Integer)
    semester: Mapped[int] = mapped_column(Integer)
    sub_class: Mapped[str] = mapped_column(String(10), default="")
    students: Mapped[int] = mapped_column(Integer)
    # How the cohort studies; ODEL students sit their exams in a room of their own.
    mode: Mapped[str] = mapped_column(String(20), default="regular")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    @property
    def label(self) -> str:
        """As the Generator prints class rows: 'BSC.CS Y1S1', 'BSC.CS Y1S1 (A)'."""
        return f"{self.programme} Y{self.year}S{self.semester}" + (
            f" ({self.sub_class})" if self.sub_class else ""
        )


class Unit(Base):
    """
    A unit a department teaches this term, with its weekly pattern and the
    courses that take it (its own or other departments'). Entered once per
    term, by the department that owns it.
    """

    __tablename__ = "units"
    __table_args__ = (
        UniqueConstraint("generator_term_id", "code_key", name="uq_unit_term_code"),
        Index("ix_unit_department", "generator_term_id", "department_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    generator_term_id: Mapped[str] = mapped_column(String(64))
    department_code: Mapped[str] = mapped_column(String(32))
    code: Mapped[str] = mapped_column(String(64))
    # The code without spaces or punctuation, upper case: 'COSC 103' and 'cosc103' are one unit.
    code_key: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255))
    weekly_hours: Mapped[int] = mapped_column(Integer)
    class_length: Mapped[int] = mapped_column(Integer)
    room_type: Mapped[str] = mapped_column(String(30), default="lecture_hall")
    # What the unit was when the department last published (services.teaching.signature);
    # None until then. A unit that differs is "changed since published".
    published_signature: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entered_by_name: Mapped[str] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    courses: Mapped[list[UnitCourse]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    groups: Mapped[list[UnitGroup]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="UnitGroup.label"
    )


class UnitCourse(Base):
    """Which courses take a unit."""

    __tablename__ = "unit_courses"

    unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"), primary_key=True)
    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courses.id", ondelete="RESTRICT"), primary_key=True, index=True
    )


class UnitGroup(Base):
    """
    One class of a unit: the whole class (label "") or one group of a split
    ("GR A"), the courses in it, its lecturer and the form's L/P/CF hours.
    The department decides the split.
    """

    __tablename__ = "unit_groups"
    __table_args__ = (UniqueConstraint("unit_id", "label", name="uq_unit_group_label"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(50), default="")
    lecturer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lecturers.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    # Semester hours as written on the department's allocation form.
    lecture_hours: Mapped[Decimal | None] = mapped_column(Numeric(6, 1), nullable=True)
    practical_hours: Mapped[Decimal | None] = mapped_column(Numeric(6, 1), nullable=True)
    cf_hours: Mapped[Decimal | None] = mapped_column(Numeric(6, 1), nullable=True)

    members: Mapped[list[UnitGroupMember]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    lecturer: Mapped[Lecturer | None] = relationship(lazy="joined")


class UnitGroupMember(Base):
    """A course in a group; `students` is its share when the course is split between groups, else None."""

    __tablename__ = "unit_group_members"

    group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("unit_groups.id", ondelete="CASCADE"), primary_key=True
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courses.id", ondelete="RESTRICT"), primary_key=True, index=True
    )
    students: Mapped[int | None] = mapped_column(Integer, nullable=True)


class DepartmentPublication(Base):
    """
    A COD publishing their department's list for a term to the Director:
    its teaching, its exam papers or its invigilators (`kind`). While it
    stands (not reopened) that list is locked; the COD reopens it to change it.
    """

    __tablename__ = "department_publications"
    __table_args__ = (Index("ix_department_publication", "generator_term_id", "department_code"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(20), default="teaching")  # teaching | exams | invigilators
    generator_term_id: Mapped[str] = mapped_column(String(64))
    department_code: Mapped[str] = mapped_column(String(32))
    department_name: Mapped[str] = mapped_column(String(255))
    published_by_account_id: Mapped[str] = mapped_column(String(64))
    published_by_name: Mapped[str] = mapped_column(String(255))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    unit_count: Mapped[int] = mapped_column(Integer)
    group_count: Mapped[int] = mapped_column(Integer)
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reopened_by_name: Mapped[str | None] = mapped_column(String(255), nullable=True)


# -- exams ------------------------------------------------------------------------------


class ExamPaper(Base):
    """
    One written exam paper a department sets this term. All groups of a unit
    sit one paper, and one paper can carry several units' codes
    ("BITE 131/COSC 130"); a unit is on at most one paper per term. The
    department entering a paper owns at least one of its units.
    """

    __tablename__ = "exam_papers"
    __table_args__ = (Index("ix_exam_paper_department", "generator_term_id", "department_code"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    generator_term_id: Mapped[str] = mapped_column(String(64))
    department_code: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255))
    examiner_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lecturers.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    notes: Mapped[str] = mapped_column(String(500), default="")
    published_signature: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    units: Mapped[list[ExamPaperUnit]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    examiner: Mapped[Lecturer | None] = relationship(lazy="joined")


class ExamPaperUnit(Base):
    """A unit sat on a paper; unique per unit, so no unit is examined twice."""

    __tablename__ = "exam_paper_units"

    paper_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exam_papers.id", ondelete="CASCADE"), primary_key=True
    )
    unit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("units.id", ondelete="CASCADE"), primary_key=True, unique=True, index=True
    )


class NoWrittenExam(Base):
    """A unit the department marked as having no written exam this term (project, practical only...)."""

    __tablename__ = "no_written_exams"

    unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"), primary_key=True)


class Practical(Base):
    """A practical exam on a date the department sets; the Generator only shows it on the timetable."""

    __tablename__ = "practicals"
    __table_args__ = (Index("ix_practical_department", "generator_term_id", "department_code"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    generator_term_id: Mapped[str] = mapped_column(String(64))
    department_code: Mapped[str] = mapped_column(String(32))
    unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)


class Invigilation(Base):
    """
    Who invigilates a paper in a room of the Director's shared exam draft.
    `paper_ref` is the paper's id here; `room` the room's code there.
    """

    __tablename__ = "invigilations"
    __table_args__ = (UniqueConstraint("paper_id", "room", name="uq_invigilation_paper_room"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    paper_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exam_papers.id", ondelete="CASCADE"), index=True)
    room: Mapped[str] = mapped_column(String(30))
    lecturer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lecturers.id", ondelete="RESTRICT"), index=True
    )
    entered_by_name: Mapped[str] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    lecturer: Mapped[Lecturer] = relationship(lazy="joined")
