"""
The Allocator's own data.

The allocation form (what departments fill in): each department's own list
of lecturers, its allocation rows (unit, group, lecturer, L/P/CF hours) for a
term of the Timetable Generator, and its submissions. Units and groups are
read from the Generator; the Allocator keeps no copy of the timetable.

Also kept from the SMARTTT-based allocation: who allocated each SMARTTT class
and when, lecturers' unavailability, departments' submissions, the audit
trail, and sign-in sessions.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
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


# -- the allocation form ---------------------------------------------------------------


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


class FormEntry(Base):
    """
    One row of a department's allocation form: a unit (or one group of it) for a
    term of the Generator, the lecturer given it, and the form's L/P/CF hours.
    `key` is the class ("COSC103-GRA"); each class has one row per term.
    """

    __tablename__ = "form_entries"
    __table_args__ = (
        UniqueConstraint("generator_term_id", "key", name="uq_form_entry_term_key"),
        Index("ix_form_entry_department", "generator_term_id", "department_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    generator_term_id: Mapped[str] = mapped_column(String(64))
    department_code: Mapped[str] = mapped_column(String(32))
    key: Mapped[str] = mapped_column(String(80))
    unit_code: Mapped[str] = mapped_column(String(64))
    unit_title: Mapped[str] = mapped_column(String(255))
    group_label: Mapped[str] = mapped_column(String(50), default="")
    # Class row labels as the Generator printed them when the row was saved.
    class_rows: Mapped[list[str]] = mapped_column(JSON, default=list)
    lecturer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lecturers.id", ondelete="RESTRICT"), nullable=True
    )
    lecture_hours: Mapped[Decimal | None] = mapped_column(Numeric(6, 1), nullable=True)
    practical_hours: Mapped[Decimal | None] = mapped_column(Numeric(6, 1), nullable=True)
    cf_hours: Mapped[Decimal | None] = mapped_column(Numeric(6, 1), nullable=True)
    entered_by_account_id: Mapped[str] = mapped_column(String(64))
    entered_by_name: Mapped[str] = mapped_column(String(255))
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    # What SMARTTT was last told for this class: its section key there, the
    # SMARTTT lecturer set on it (None: cleared) and which of this form's
    # lecturers that was ("" for none), so a change is sent once and SMARTTT
    # can refuse a stale one. `smarttt_error` says why the last try failed.
    smarttt_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    smarttt_lecturer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    smarttt_sent_for: Mapped[str | None] = mapped_column(String(64), nullable=True)
    smarttt_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    smarttt_error: Mapped[str | None] = mapped_column(String(500), nullable=True)

    lecturer: Mapped[Lecturer | None] = relationship(lazy="joined")


class FormSubmission(Base):
    """A COD submitting their department's allocation form for a term; reopening ends it."""

    __tablename__ = "form_submissions"
    __table_args__ = (Index("ix_form_submission_department", "generator_term_id", "department_code"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    generator_term_id: Mapped[str] = mapped_column(String(64))
    department_code: Mapped[str] = mapped_column(String(32))
    submitted_by_account_id: Mapped[str] = mapped_column(String(64))
    submitted_by_name: Mapped[str] = mapped_column(String(255))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    entry_count: Mapped[int] = mapped_column(Integer)
    allocated_count: Mapped[int] = mapped_column(Integer)
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reopened_by_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
