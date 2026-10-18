"""
Allocating lecturers to a department's published classes.

A *section* is one unit taught to one group ("COSC 103 GR A"), identified by
SMARTTT's section key ("412-GRA"). The department that owns the unit
allocates it, including classes it teaches to other departments' students.

Checks before a lecturer is given a section:
- H11: not teaching anything else at any of the section's hours;
- H12: not marked unavailable then, and not past max_weekly_teaching_hours.

The Allocator checks these first for quick, explained feedback (and is the
only one that knows about unavailability); SMARTTT re-checks H11 and the
weekly hours under a lock when the allocation is saved, and its answer wins.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth import Identity
from app.clients.smarttt import SmartttClient
from app.errors import ApiError
from app.models import (
    Allocation,
    AllocationStatus,
    AuditLog,
    LecturerAvailability,
    Submission,
    Term,
    utcnow,
)
from app.services.timeutil import hhmm, overlaps, weekly_hours


def ensure_term(db: Session, term: dict[str, Any]) -> Term:
    """The local row for a SMARTTT term, created on first use."""
    row = db.scalar(select(Term).where(Term.smarttt_term_id == term["id"]))
    if row is None:
        row = Term(smarttt_term_id=term["id"], academic_year=term["academic_year"], semester=term["semester"])
        db.add(row)
        db.flush()
    return row


def require_view(identity: Identity, department_id: int) -> None:
    if not identity.can_view(department_id):
        raise ApiError(403, "FORBIDDEN", "You can only see your own department's allocation.")


def require_allocate(identity: Identity, department_id: int) -> None:
    if not identity.can_allocate(department_id):
        raise ApiError(
            403, "FORBIDDEN", "Only this department's COD and allocation staff can allocate its classes."
        )


def audit(
    db: Session,
    identity: Identity,
    action: str,
    entity: str,
    entity_id: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    db.add(
        AuditLog(
            actor_account_id=identity.account_id,
            actor_name=identity.actor,
            action=action,
            entity=entity,
            entity_id=entity_id,
            before=before,
            after=after,
        )
    )


def _num(value: Decimal | float | None) -> float | None:
    return float(value) if value is not None else None


def allocation_dict(row: Allocation | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "lecturer_id": row.smarttt_lecturer_id,
        "lecturer_name": row.lecturer_name,
        "employment_type": row.employment_type,
        "lecture_hours": _num(row.lecture_hours),
        "practical_hours": _num(row.practical_hours),
        "cf_hours": _num(row.cf_hours),
        "entered_by": row.entered_by_name,
        "entered_at": row.entered_at.isoformat(),
        "synced_to_smarttt_at": row.synced_to_smarttt_at.isoformat() if row.synced_to_smarttt_at else None,
        "status": row.status.value,
    }


def section_state(section: dict[str, Any]) -> str:
    if section.get("lecturer_conflict"):
        return "conflict"
    if section.get("lecturer"):
        return "allocated"
    if section.get("lecturer_name_text"):
        return "unmatched"  # named on an older allocation document, no SMARTTT account linked
    return "outstanding"


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def latest_submission(db: Session, term: Term, department_id: int) -> Submission | None:
    return db.scalar(
        select(Submission)
        .where(Submission.term_id == term.id, Submission.department_id == department_id)
        .order_by(Submission.submitted_at.desc())
        .limit(1)
    )


def submission_dict(row: Submission | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "submitted_by": row.submitted_by_name,
        "submitted_at": row.submitted_at.isoformat(),
        "section_count": row.section_count,
        "allocated_count": row.allocated_count,
        "superseded_at": row.superseded_at.isoformat() if row.superseded_at else None,
        "is_current": row.superseded_at is None,
    }


def department_board(
    db: Session, smarttt: SmartttClient, identity: Identity, department_id: int, term_id: str | None
) -> dict[str, Any]:
    """Everything the department's allocation screen shows."""
    require_view(identity, department_id)
    data = smarttt.sections(department_id, term_id)
    term = ensure_term(db, data["term"])
    local = {
        a.section_key: a
        for a in db.scalars(
            select(Allocation).where(
                Allocation.term_id == term.id, Allocation.smarttt_department_id == department_id
            )
        )
    }
    sections = []
    for section in data["sections"]:
        sections.append(
            {
                **section,
                "state": section_state(section),
                "servicing": any(
                    row.get("program_department_id") not in (None, department_id)
                    for row in section["class_rows"]
                ),
                "allocation": allocation_dict(local.get(section["key"])),
            }
        )
    db.commit()
    summary = _summary(sections)
    return {
        "term": data["term"],
        "department_id": department_id,
        "role": identity.role_in(department_id),
        "can_allocate": identity.can_allocate(department_id),
        "can_submit": identity.can_submit(department_id),
        "sections": sections,
        "summary": summary,
        "submission": submission_dict(latest_submission(db, term, department_id)),
    }


def _summary(sections: list[dict[str, Any]]) -> dict[str, int]:
    states = [s["state"] for s in sections]
    return {
        "sections": len(sections),
        "allocated": states.count("allocated"),
        "outstanding": states.count("outstanding") + states.count("unmatched"),
        "conflicts": states.count("conflict"),
    }


# ---------------------------------------------------------------------------
# Who can take a section
# ---------------------------------------------------------------------------


def _unavailable_periods(db: Session, term: Term) -> dict[str, list[dict[str, Any]]]:
    periods: dict[str, list[dict[str, Any]]] = {}
    for row in db.scalars(select(LecturerAvailability).where(LecturerAvailability.term_id == term.id)):
        periods.setdefault(row.smarttt_lecturer_id, []).append(
            {
                "day_of_week": row.day,
                "start_time": hhmm(row.start_time),
                "end_time": hhmm(row.end_time),
                "reason": row.reason,
            }
        )
    return periods


@dataclass
class Assessment:
    clashes: list[dict[str, Any]]
    unavailable: list[dict[str, Any]]
    weekly_hours_after: float
    over_limit: bool

    @property
    def free(self) -> bool:
        return not self.clashes and not self.unavailable and not self.over_limit


def assess(
    section: dict[str, Any], lecturer: dict[str, Any], unavailable: list[dict[str, Any]]
) -> Assessment:
    """Whether a lecturer (with their `meetings` this term) can take the section, and why not."""
    key = section["key"]
    others = [m for m in lecturer.get("meetings", []) if m["section_key"] != key]
    clashes = [
        {
            "day_of_week": m["day_of_week"],
            "start_time": m["start_time"],
            "end_time": m["end_time"],
            "clashes_with": o["code"],
        }
        for m in section["meetings"]
        for o in others
        if overlaps(m, o)
    ]
    blocked = [
        {
            "day_of_week": m["day_of_week"],
            "start_time": m["start_time"],
            "end_time": m["end_time"],
            "reason": u["reason"],
        }
        for m in section["meetings"]
        for u in unavailable
        if overlaps(m, u)
    ]
    mine = [
        {"day_of_week": m["day_of_week"], "start_time": m["start_time"], "end_time": m["end_time"]}
        for m in section["meetings"]
    ]
    hours = weekly_hours(others + mine)
    return Assessment(
        clashes=clashes,
        unavailable=blocked,
        weekly_hours_after=hours,
        over_limit=hours > lecturer["max_weekly_teaching_hours"],
    )


def free_lecturers(
    db: Session, smarttt: SmartttClient, identity: Identity, key: str, term_id: str | None, scope: str
) -> dict[str, Any]:
    """
    Every candidate lecturer for the section, free ones first, each with the
    reasons they can't take it. `scope` "department" = the owning
    department's lecturers, "all" = every department's (e.g. for part-timers
    attached elsewhere).
    """
    data = smarttt.section(key, term_id)
    section = data["section"]
    department_id = int(section["unit"]["department_id"])
    require_view(identity, department_id)
    term = ensure_term(db, data["term"])
    lecturers = smarttt.lecturers(department_id if scope == "department" else None, data["term"]["id"])
    periods = _unavailable_periods(db, term)
    db.commit()

    current = (section.get("lecturer") or {}).get("id")
    candidates = []
    for lecturer in lecturers:
        result = assess(section, lecturer, periods.get(lecturer["id"], []))
        candidates.append(
            {
                "lecturer": {k: v for k, v in lecturer.items() if k != "meetings"},
                "free": result.free,
                "current": lecturer["id"] == current,
                "weekly_hours": lecturer.get("weekly_hours", 0.0),
                "weekly_hours_after": result.weekly_hours_after,
                "clashes": result.clashes,
                "unavailable": result.unavailable,
                "over_limit": result.over_limit,
            }
        )
    candidates.sort(
        key=lambda c: (not c["current"], not c["free"], c["weekly_hours"], c["lecturer"]["full_name"])
    )
    return {"term": data["term"], "section": section, "candidates": candidates}


# ---------------------------------------------------------------------------
# Saving an allocation
# ---------------------------------------------------------------------------


def set_allocation(
    db: Session,
    smarttt: SmartttClient,
    identity: Identity,
    key: str,
    term_id: str | None,
    lecturer_id: str | None,
    expected_lecturer_id: str | None,
    hours: dict[str, float | None],
) -> dict[str, Any]:
    data = smarttt.section(key, term_id, fresh=True)
    section = data["section"]
    department_id = int(section["unit"]["department_id"])
    require_allocate(identity, department_id)
    term = ensure_term(db, data["term"])

    lecturer: dict[str, Any] | None = None
    if lecturer_id is not None:
        lecturer = smarttt.lecturer_sessions(lecturer_id, data["term"]["id"], fresh=True)["lecturer"]
        periods = _unavailable_periods(db, term).get(lecturer_id, [])
        blocked = [
            {
                "day_of_week": m["day_of_week"],
                "start_time": m["start_time"],
                "end_time": m["end_time"],
                "reason": u["reason"],
            }
            for m in section["meetings"]
            for u in periods
            if overlaps(m, u)
        ]
        if blocked:
            raise ApiError(
                409,
                "LECTURER_UNAVAILABLE",
                f"{lecturer['full_name']} is marked unavailable at this class's time.",
                {"unavailable": blocked},
            )

    result = smarttt.set_lecturer(key, data["term"]["id"], lecturer_id, expected_lecturer_id)
    saved = result["section"]

    row = db.scalar(select(Allocation).where(Allocation.term_id == term.id, Allocation.section_key == key))
    before = allocation_dict(row)
    if row is None:
        row = Allocation(
            term_id=term.id,
            section_key=key,
            section_code=section["code"],
            group_label=section.get("group"),
            smarttt_unit_id=int(section["unit"]["id"]),
            smarttt_department_id=department_id,
            entered_by_account_id=identity.account_id,
            entered_by_name=identity.actor,
        )
        db.add(row)
    row.section_code = section["code"]
    row.smarttt_lecturer_id = lecturer_id
    row.lecturer_name = lecturer["full_name"] if lecturer else None
    row.employment_type = lecturer["employment_type"] if lecturer else None
    row.lecture_hours = _decimal(hours.get("lecture_hours"))
    row.practical_hours = _decimal(hours.get("practical_hours"))
    row.cf_hours = _decimal(hours.get("cf_hours"))
    row.entered_by_account_id = identity.account_id
    row.entered_by_name = identity.actor
    row.entered_at = utcnow()
    row.synced_to_smarttt_at = utcnow()
    row.status = AllocationStatus.SAVED
    db.flush()
    after = allocation_dict(row)
    audit(db, identity, "allocation.set", "section", f"{term.smarttt_term_id}:{key}", before, after)
    if before != after:
        _supersede_submission(db, term, department_id)
    db.commit()
    return {
        "term": data["term"],
        "section": {**saved, "state": section_state(saved), "allocation": after},
        "changed_in_smarttt": result["changed"],
    }


def _decimal(value: float | None) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def _supersede_submission(db: Session, term: Term, department_id: int) -> None:
    """Changing an allocation after the COD submitted reopens the department's allocation."""
    db.execute(
        update(Submission)
        .where(
            Submission.term_id == term.id,
            Submission.department_id == department_id,
            Submission.superseded_at.is_(None),
        )
        .values(superseded_at=utcnow())
    )
    db.execute(
        update(Allocation)
        .where(
            Allocation.term_id == term.id,
            Allocation.smarttt_department_id == department_id,
            Allocation.status == AllocationStatus.SUBMITTED,
        )
        .values(status=AllocationStatus.SAVED)
    )


# ---------------------------------------------------------------------------
# Submitting and progress
# ---------------------------------------------------------------------------


def submit(
    db: Session, smarttt: SmartttClient, identity: Identity, department_id: int, term_id: str | None
) -> dict[str, Any]:
    if not identity.can_submit(department_id):
        raise ApiError(403, "FORBIDDEN", "Only the department's COD can submit its allocation.")
    data = smarttt.sections(department_id, term_id, fresh=True)
    term = ensure_term(db, data["term"])
    sections = [{**s, "state": section_state(s)} for s in data["sections"]]
    if not sections:
        raise ApiError(409, "NOTHING_TO_SUBMIT", "This department has no published classes this term.")
    pending = [s["code"] for s in sections if s["state"] != "allocated"]
    if pending:
        raise ApiError(
            409,
            "ALLOCATION_INCOMPLETE",
            f"{len(pending)} classes still need a lecturer before the allocation can be submitted.",
            {"sections": pending},
        )

    _supersede_submission(db, term, department_id)
    submission = Submission(
        term_id=term.id,
        department_id=department_id,
        submitted_by_account_id=identity.account_id,
        submitted_by_name=identity.actor,
        section_count=len(sections),
        allocated_count=len(sections),
    )
    db.add(submission)
    db.execute(
        update(Allocation)
        .where(Allocation.term_id == term.id, Allocation.smarttt_department_id == department_id)
        .values(status=AllocationStatus.SUBMITTED)
    )
    db.flush()
    audit(
        db,
        identity,
        "allocation.submit",
        "department",
        f"{term.smarttt_term_id}:{department_id}",
        None,
        {"section_count": len(sections)},
    )
    db.commit()
    return {"term": data["term"], "submission": submission_dict(submission)}


def department_progress(
    db: Session, smarttt: SmartttClient, identity: Identity, department_id: int, term_id: str | None
) -> dict[str, Any]:
    require_view(identity, department_id)
    data = smarttt.sections(department_id, term_id)
    term = ensure_term(db, data["term"])
    sections = [{**s, "state": section_state(s)} for s in data["sections"]]
    result = {
        "term": data["term"],
        "department_id": department_id,
        **_summary(sections),
        "submission": submission_dict(latest_submission(db, term, department_id)),
    }
    db.commit()
    return result


def all_progress(
    db: Session, smarttt: SmartttClient, identity: Identity, term_id: str | None
) -> dict[str, Any]:
    """Every department's progress, for the Directorate."""
    if not identity.timetabling_office:
        raise ApiError(
            403, "FORBIDDEN", "Only the Directorate of Examinations and Timetabling sees every department."
        )
    departments = smarttt.departments()
    rows = []
    term_data: dict[str, Any] | None = None
    for department in departments:
        progress = department_progress(db, smarttt, identity, int(department["id"]), term_id)
        term_data = progress.pop("term")
        if progress["sections"]:
            rows.append({"department": department, **progress})
    return {"term": term_data, "departments": rows}
