"""
The allocation form: what each department fills in, replacing the Word form.

A department keeps its own list of lecturers and, for a term of the Timetable
Generator, gives each of its units (or each group of a split unit) a lecturer
and the form's L, P and CF hours. Units and groups come from the Generator;
a unit the Generator doesn't have yet can still be typed in, and is flagged.

Once the Director publishes the timetable, every class has its meetings, and
a lecturer is refused for a class that would put them in two places at once,
or over their weekly teaching hours. One person on two departments' lists
(same staff number) is checked as one person.

Departments are identified by their code in the Generator ("DCOMP"); a
signed-in member of staff belongs to a department when SMARTTT lists them
under it (matched on SMARTTT's department id, the code, or the name).
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import ROLE_COD, Identity
from app.clients.generator import GeneratorClient
from app.clients.smarttt import SmartttClient
from app.errors import ApiError
from app.models import EmploymentType, FormEntry, FormSubmission, Lecturer, utcnow
from app.services import smarttt_sync
from app.services.allocation import audit
from app.services.timeutil import DAY_ORDER, minutes, overlaps

EMPLOYMENT_SHORT = {EmploymentType.FULL_TIME: "FT", EmploymentType.PART_TIME: "PT"}


def compact(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def form_key(unit_code: str, group_label: str) -> str:
    """'COSC 103', 'GR A' -> 'COSC103-GRA'; a whole unit -> 'COSC103-MAIN', as the Generator keys it."""
    return f"{compact(unit_code)}-{compact(group_label) or 'MAIN'}"


def _num(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _dec(value: float | None) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


# -- terms, departments and who may do what ------------------------------------------


@dataclass
class Context:
    term: dict[str, Any]
    sections: list[dict[str, Any]]
    published_version: int | None
    department: dict[str, Any]
    role: str | None  # cod | admin | editor | None (viewing only)
    in_smarttt: bool = False  # SMARTTT has the Director's latest version: lecturers can be sent

    def smarttt_target(self, section: dict[str, Any] | None) -> smarttt_sync.Target:
        return smarttt_sync.target(self.term, self.in_smarttt, section)


def pick_term(generator: GeneratorClient, term_id: str | None) -> dict[str, Any]:
    terms = generator.terms()
    if not terms:
        raise ApiError(404, "NO_TERM", "The Timetable Generator has no term yet.")
    if term_id is None:
        return terms[0]
    found = next((t for t in terms if t["id"] == term_id), None)
    if found is None:
        raise ApiError(404, "NOT_FOUND", "The Timetable Generator has no such term.")
    return found


def _role_for(identity: Identity, department: dict[str, Any]) -> str | None:
    for d in identity.departments:
        if (
            (department.get("smarttt_id") is not None and department["smarttt_id"] == d.id)
            or compact(d.code) == compact(department["code"])
            or d.name.strip().lower() == str(department.get("name") or "").strip().lower()
        ):
            return d.role
    return None


def generator_departments(sections: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """The departments that own units in the term, by compact code."""
    found: dict[str, dict[str, Any]] = {}
    for s in sections:
        d = s.get("department")
        if d:
            found.setdefault(compact(d["code"]), d)
    return found


def visible_departments(identity: Identity, sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The departments this person may open: all for the Directorate, else their own."""
    owners = generator_departments(sections)
    out: dict[str, dict[str, Any]] = {}
    matched: set[str] = set()
    for key, d in owners.items():
        role = _role_for(identity, d)
        if role is not None:
            matched.update(
                compact(m.code) for m in identity.departments if _role_for(_only(identity, m), d) is not None
            )
        if role is not None or identity.timetabling_office:
            out[key] = {"code": d["code"], "name": d["name"], "role": role}
    # A department with no units in the Generator yet can still fill in its form.
    for m in identity.departments:
        if compact(m.code) not in matched:
            out.setdefault(compact(m.code), {"code": m.code, "name": m.name, "role": m.role})
    return sorted(out.values(), key=lambda d: d["name"])


def _only(identity: Identity, department: Any) -> Identity:
    """The same person, with just one of their departments (to tell which one matched)."""

    return replace(identity, departments=(department,))


def context(
    generator: GeneratorClient, identity: Identity, department_code: str, term_id: str | None
) -> Context:
    term = pick_term(generator, term_id)
    data = generator.sections(term["id"])
    sections = list(data.get("sections") or [])
    owners = generator_departments(sections)
    department = owners.get(compact(department_code))
    if department is None:
        mine = next((d for d in identity.departments if compact(d.code) == compact(department_code)), None)
        if mine is None and not identity.timetabling_office:
            raise ApiError(403, "FORBIDDEN", "You can only open your own department's allocation.")
        department = {
            "code": mine.code if mine else department_code,
            "name": mine.name if mine else department_code,
        }
    role = _role_for(identity, department)
    if role is None and not identity.timetabling_office:
        raise ApiError(403, "FORBIDDEN", "You can only open your own department's allocation.")
    return Context(
        term=term,
        sections=sections,
        published_version=data.get("published_version"),
        department={"code": department["code"], "name": department["name"]},
        role=role,
        in_smarttt=bool(data.get("in_smarttt")),
    )


def _require_allocate(ctx: Context) -> None:
    if ctx.role is None:
        raise ApiError(
            403, "FORBIDDEN", "Only this department's COD and allocation staff can change its allocation."
        )


def _require_cod(ctx: Context) -> None:
    if ctx.role != ROLE_COD:
        raise ApiError(403, "FORBIDDEN", "Only the Chair of Department can submit or reopen the allocation.")


def _code(ctx: Context) -> str:
    return compact(ctx.department["code"])


def current_submission(db: Session, term_id: str, department_code: str) -> FormSubmission | None:
    return db.scalar(
        select(FormSubmission)
        .where(
            FormSubmission.generator_term_id == term_id,
            FormSubmission.department_code == department_code,
            FormSubmission.reopened_at.is_(None),
        )
        .order_by(FormSubmission.submitted_at.desc())
        .limit(1)
    )


def _require_open(db: Session, ctx: Context) -> None:
    if current_submission(db, ctx.term["id"], _code(ctx)) is not None:
        raise ApiError(
            409,
            "FORM_SUBMITTED",
            "This allocation has been submitted. The COD must reopen it before it can change.",
        )


# -- lecturers ------------------------------------------------------------------------------


def lecturer_dict(lecturer: Lecturer, show_contacts: bool = True) -> dict[str, Any]:
    return {
        "id": str(lecturer.id),
        "department_code": lecturer.department_code,
        "title": lecturer.title,
        "full_name": lecturer.full_name,
        "staff_number": lecturer.staff_number,
        "employment_type": lecturer.employment_type.value,
        "phone": lecturer.phone if show_contacts else "",
        "email": lecturer.email if show_contacts else "",
        "max_weekly_hours": lecturer.max_weekly_hours,
        "active": lecturer.active,
    }


def display_name(lecturer: Lecturer) -> str:
    title = f"{lecturer.title} " if lecturer.title else ""
    return f"{title}{lecturer.full_name} ({EMPLOYMENT_SHORT[lecturer.employment_type]})"


def department_lecturers(db: Session, department_code: str) -> list[Lecturer]:
    return list(
        db.scalars(
            select(Lecturer).where(Lecturer.department_code == department_code).order_by(Lecturer.full_name)
        )
    )


def _apply_lecturer(db: Session, lecturer: Lecturer, fields: dict[str, Any]) -> None:
    staff = fields.get("staff_number")
    if staff:
        staff = staff.strip().upper()
        clash = db.scalar(
            select(Lecturer).where(
                Lecturer.department_code == lecturer.department_code,
                func.upper(Lecturer.staff_number) == staff,
                Lecturer.id != lecturer.id,
            )
        )
        if clash is not None:
            raise ApiError(409, "STAFF_NUMBER_TAKEN", f"{staff} is already on the list as {clash.full_name}.")
        fields = {**fields, "staff_number": staff}
    for key in ("title", "full_name", "staff_number", "phone", "email", "max_weekly_hours", "active"):
        if key in fields:
            setattr(lecturer, key, fields[key] if fields[key] != "" or key != "staff_number" else None)
    if fields.get("employment_type") is not None:
        lecturer.employment_type = EmploymentType(fields["employment_type"])


def create_lecturer(
    db: Session, identity: Identity, ctx: Context, fields: dict[str, Any], commit: bool = True
) -> Lecturer:
    _require_allocate(ctx)
    lecturer = Lecturer(department_code=_code(ctx), full_name="", title="", phone="", email="")
    _apply_lecturer(db, lecturer, fields)
    db.add(lecturer)
    db.flush()
    audit(db, identity, "lecturer.create", "lecturer", str(lecturer.id), None, lecturer_dict(lecturer))
    if commit:
        db.commit()
    return lecturer


def get_lecturer(db: Session, lecturer_id: str) -> Lecturer:
    try:
        found = db.get(Lecturer, uuid.UUID(lecturer_id))
    except ValueError:
        found = None
    if found is None:
        raise ApiError(404, "NOT_FOUND", "No such lecturer.")
    return found


def update_lecturer(
    db: Session, identity: Identity, ctx: Context, lecturer: Lecturer, fields: dict[str, Any]
) -> Lecturer:
    _require_allocate(ctx)
    before = lecturer_dict(lecturer)
    _apply_lecturer(db, lecturer, fields)
    db.flush()
    audit(db, identity, "lecturer.update", "lecturer", str(lecturer.id), before, lecturer_dict(lecturer))
    db.commit()
    return lecturer


def delete_lecturer(db: Session, identity: Identity, ctx: Context, lecturer: Lecturer) -> None:
    _require_allocate(ctx)
    used = db.scalar(select(func.count()).select_from(FormEntry).where(FormEntry.lecturer_id == lecturer.id))
    if used:
        raise ApiError(
            409,
            "IN_USE",
            f"{lecturer.full_name} is allocated {used} classes. Change those first, or mark them inactive.",
        )
    audit(db, identity, "lecturer.delete", "lecturer", str(lecturer.id), lecturer_dict(lecturer), None)
    db.delete(lecturer)
    db.commit()


def lecturer_ctx_check(lecturer: Lecturer, ctx: Context) -> None:
    if lecturer.department_code != _code(ctx):
        raise ApiError(403, "FORBIDDEN", "That lecturer is on another department's list.")


# -- the form -------------------------------------------------------------------------------


def person(lecturer: Lecturer) -> str:
    """One person across departments' lists: the staff number when known."""
    return f"staff:{lecturer.staff_number.upper()}" if lecturer.staff_number else f"id:{lecturer.id}"


def _when(m: dict[str, str]) -> str:
    return f"{m['day_of_week']} {m['start_time']}-{m['end_time']}"


def _hours(meetings: list[dict[str, str]]) -> float:
    distinct = {(m["day_of_week"], m["start_time"], m["end_time"]) for m in meetings}
    return round(sum(minutes(s, e) for _d, s, e in distinct) / 60, 2)


def _term_entries(db: Session, term_id: str) -> list[FormEntry]:
    return list(db.scalars(select(FormEntry).where(FormEntry.generator_term_id == term_id)))


def check_lecturer(
    db: Session,
    term_id: str,
    lecturer: Lecturer,
    key: str,
    meetings_by_key: dict[str, list[dict[str, str]]],
    entries: list[FormEntry] | None = None,
) -> list[dict[str, str]]:
    """Why this lecturer can't take this class: a clash with another of their classes, or too many hours."""
    mine = meetings_by_key.get(key) or []
    who = person(lecturer)
    others = [
        e
        for e in (entries if entries is not None else _term_entries(db, term_id))
        if e.key != key and e.lecturer is not None and person(e.lecturer) == who
    ]
    problems: list[dict[str, str]] = []
    for e in others:
        for a in mine:
            hit = next((b for b in meetings_by_key.get(e.key) or [] if overlaps(a, b)), None)
            if hit is not None:
                problems.append(
                    {
                        "code": "clash",
                        "message": f"{lecturer.full_name} already teaches {e.unit_code}"
                        f"{' ' + e.group_label if e.group_label else ''} on {_when(hit)}.",
                    }
                )
                break
    if lecturer.max_weekly_hours and mine:
        week = [m for e in others for m in meetings_by_key.get(e.key) or []] + mine
        total = _hours(week)
        if total > lecturer.max_weekly_hours:
            problems.append(
                {
                    "code": "over_hours",
                    "message": f"{lecturer.full_name} would teach {total:g} hours a week; "
                    f"the limit is {lecturer.max_weekly_hours}.",
                }
            )
    return problems


def _section_row(
    section: dict[str, Any] | None,
    entry: FormEntry | None,
    department_code: str,
    problems: list[dict[str, str]],
    smarttt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    smarttt = smarttt or {"state": None, "message": None}
    if section is not None:
        class_rows = [
            {
                "label": r["label"],
                "students": r.get("students"),
                "department_code": (r.get("department") or {}).get("code"),
            }
            for r in section.get("class_rows") or []
        ]
        servicing = any(
            r["department_code"] and compact(r["department_code"]) != department_code for r in class_rows
        )
        return {
            "key": section["key"],
            "unit_code": section["unit_code"],
            "unit_title": section["unit_name"],
            "group": section.get("group") or "",
            "class_rows": class_rows,
            "students": section.get("students"),
            "weekly_hours": section.get("weekly_hours"),
            "meetings": section.get("meetings") or [],
            "servicing": servicing,
            "in_timetable": True,
            "entry": entry_dict(entry),
            "problems": problems,
            "smarttt": smarttt,
        }
    assert entry is not None
    return {
        "key": entry.key,
        "unit_code": entry.unit_code,
        "unit_title": entry.unit_title,
        "group": entry.group_label,
        "class_rows": [
            {"label": label, "students": None, "department_code": None} for label in entry.class_rows
        ],
        "students": None,
        "weekly_hours": None,
        "meetings": [],
        "servicing": False,
        "in_timetable": False,
        "entry": entry_dict(entry),
        "problems": problems,
        "smarttt": smarttt,
    }


def entry_dict(entry: FormEntry | None) -> dict[str, Any] | None:
    if entry is None:
        return None
    return {
        "id": str(entry.id),
        "lecturer_id": str(entry.lecturer_id) if entry.lecturer_id else None,
        "lecturer": display_name(entry.lecturer) if entry.lecturer else None,
        "lecture_hours": _num(entry.lecture_hours),
        "practical_hours": _num(entry.practical_hours),
        "cf_hours": _num(entry.cf_hours),
        "entered_by": entry.entered_by_name,
        "entered_at": entry.entered_at.isoformat(),
    }


def board(
    db: Session, generator: GeneratorClient, identity: Identity, department_code: str, term_id: str | None
) -> dict[str, Any]:
    ctx = context(generator, identity, department_code, term_id)
    code = _code(ctx)
    meetings_by_key = {s["key"]: s.get("meetings") or [] for s in ctx.sections}
    own = [s for s in ctx.sections if s.get("department") and compact(s["department"]["code"]) == code]
    own_keys = {s["key"] for s in own}
    term_entries = _term_entries(db, ctx.term["id"])
    # A unit split into groups (or merged back) after it was allocated leaves an
    # entry for a group the timetable no longer has: it is not shown, counted or printed.
    timetabled = {compact(s["unit_code"]) for s in own}
    mine = {
        e.key: e
        for e in term_entries
        if e.department_code == code and (e.key in own_keys or compact(e.unit_code) not in timetabled)
    }

    rows = []
    for s in own:
        entry = mine.get(s["key"])
        problems = (
            check_lecturer(db, ctx.term["id"], entry.lecturer, s["key"], meetings_by_key, term_entries)
            if entry is not None and entry.lecturer is not None
            else []
        )
        rows.append(_section_row(s, entry, code, problems, smarttt_sync.status(entry, ctx.smarttt_target(s))))
    for key, entry in mine.items():
        if key not in own_keys:
            rows.append(
                _section_row(None, entry, code, [], smarttt_sync.status(entry, ctx.smarttt_target(None)))
            )
    rows.sort(key=lambda r: (r["unit_code"], r["group"]))

    lecturers = department_lecturers(db, code)
    load: dict[uuid.UUID, dict[str, Any]] = {
        lec.id: {"classes": 0, "meetings": [], "lecture_hours": 0.0, "practical_hours": 0.0}
        for lec in lecturers
    }
    for e in mine.values():
        if e.lecturer_id in load:
            item = load[e.lecturer_id]
            item["classes"] += 1
            item["meetings"].extend(meetings_by_key.get(e.key) or [])
            item["lecture_hours"] += float(e.lecture_hours or 0)
            item["practical_hours"] += float(e.practical_hours or 0)
    submission = current_submission(db, ctx.term["id"], code)
    show_contacts = ctx.role is not None or identity.timetabling_office
    return {
        "term": ctx.term,
        "published_version": ctx.published_version,
        "department": ctx.department,
        "role": ctx.role,
        "can_edit": ctx.role is not None and submission is None,
        "can_submit": ctx.role == ROLE_COD,
        "rows": rows,
        "summary": {
            "classes": len(rows),
            "allocated": sum(1 for r in rows if r["entry"] and r["entry"]["lecturer_id"]),
            "not_in_timetable": sum(1 for r in rows if not r["in_timetable"]),
            # Allocations SMARTTT doesn't have as on the form: not published yet, refused, or unmatched.
            "not_in_smarttt": sum(1 for r in rows if r["smarttt"]["state"] in smarttt_sync.UNPUBLISHED),
            "problems": sum(1 for r in rows if r["problems"]),
        },
        "lecturers": [
            {
                **lecturer_dict(lec, show_contacts),
                "display": display_name(lec),
                "classes": load[lec.id]["classes"],
                "weekly_hours": _hours(load[lec.id]["meetings"]),
                "lecture_hours": load[lec.id]["lecture_hours"],
                "practical_hours": load[lec.id]["practical_hours"],
            }
            for lec in lecturers
        ],
        "submission": (
            {
                "submitted_by": submission.submitted_by_name,
                "submitted_at": submission.submitted_at.isoformat(),
                "entry_count": submission.entry_count,
                "allocated_count": submission.allocated_count,
            }
            if submission
            else None
        ),
    }


def save_entry(
    db: Session,
    generator: GeneratorClient,
    identity: Identity,
    department_code: str,
    term_id: str | None,
    fields: dict[str, Any],
    ctx: Context | None = None,
    commit: bool = True,
) -> dict[str, Any]:
    """
    Adds or changes one row of the form. A unit in the Generator must belong to
    this department; its title and class rows come from the Generator. A
    lecturer is refused for a class that clashes with another of their
    classes, or takes them over their weekly hours. SMARTTT gets it when the
    COD submits (publishes) the form.
    """
    ctx = ctx or context(generator, identity, department_code, term_id)
    _require_allocate(ctx)
    _require_open(db, ctx)
    code = _code(ctx)
    key = form_key(fields["unit_code"], fields.get("group_label") or "")
    sections = {s["key"]: s for s in ctx.sections}
    section = sections.get(key)
    if (
        section is None
        and not (fields.get("group_label") or "")
        and any(k.startswith(f"{compact(fields['unit_code'])}-") for k in sections)
    ):
        groups = sorted(
            s.get("group") or ""
            for k, s in sections.items()
            if k.startswith(f"{compact(fields['unit_code'])}-")
        )
        raise ApiError(
            422,
            "GROUP_REQUIRED",
            f"{fields['unit_code']} is split into groups ({', '.join(groups)}); choose the group.",
        )
    if section is not None:
        owner = section.get("department") or {}
        if compact(owner.get("code", "")) != code:
            raise ApiError(
                403,
                "NOT_YOUR_UNIT",
                f"{section['unit_code']} belongs to {owner.get('name', 'another department')}, "
                "which allocates it.",
            )
        title = section["unit_name"]
        unit_code = section["unit_code"]
        group = section.get("group") or ""
        class_rows = [r["label"] for r in section.get("class_rows") or []]
    else:
        title = (fields.get("unit_title") or "").strip()
        if not title:
            raise ApiError(422, "VALIDATION_ERROR", "This unit isn't in the timetable yet; give its title.")
        unit_code = fields["unit_code"].strip()
        group = (fields.get("group_label") or "").strip()
        class_rows = list(fields.get("class_rows") or [])

    lecturer = None
    if fields.get("lecturer_id"):
        lecturer = get_lecturer(db, str(fields["lecturer_id"]))
        lecturer_ctx_check(lecturer, ctx)
        if not lecturer.active:
            raise ApiError(422, "VALIDATION_ERROR", f"{lecturer.full_name} is marked inactive.")
        problems = check_lecturer(
            db, ctx.term["id"], lecturer, key, {k: s.get("meetings") or [] for k, s in sections.items()}
        )
        if problems:
            raise ApiError(409, "LECTURER_UNAVAILABLE", problems[0]["message"], {"problems": problems})

    entry = db.scalar(
        select(FormEntry).where(FormEntry.generator_term_id == ctx.term["id"], FormEntry.key == key)
    )
    if entry is not None and entry.department_code != code:
        raise ApiError(409, "TAKEN", f"{unit_code} {group} is on another department's form.")
    before = entry_dict(entry)
    if entry is None:
        entry = FormEntry(generator_term_id=ctx.term["id"], department_code=code, key=key)
        db.add(entry)
    entry.unit_code = unit_code
    entry.unit_title = title
    entry.group_label = group
    entry.class_rows = class_rows
    entry.lecturer_id = lecturer.id if lecturer else None
    entry.lecturer = lecturer
    entry.smarttt_error = None  # changed: SMARTTT's last answer was about the old allocation
    for name in ("lecture_hours", "practical_hours", "cf_hours"):
        if name in fields:
            setattr(entry, name, _dec(fields[name]))
    entry.entered_by_account_id = identity.account_id
    entry.entered_by_name = identity.actor
    entry.entered_at = utcnow()
    where = ctx.smarttt_target(section)
    db.flush()
    audit(db, identity, "form_entry.save", "form_entry", str(entry.id), before, entry_dict(entry))
    if commit:
        db.commit()
    return _section_row(section, entry, code, [], smarttt_sync.status(entry, where))


def delete_entry(
    db: Session,
    generator: GeneratorClient,
    identity: Identity,
    department_code: str,
    term_id: str | None,
    entry_id: str,
) -> None:
    """
    Clears a row. A row whose lecturer was published to SMARTTT stays, without
    lecturer or hours, so the next publish takes that lecturer off the class there.
    """
    ctx = context(generator, identity, department_code, term_id)
    _require_allocate(ctx)
    _require_open(db, ctx)
    try:
        entry = db.get(FormEntry, uuid.UUID(entry_id))
    except ValueError:
        entry = None
    if entry is None or entry.department_code != _code(ctx) or entry.generator_term_id != ctx.term["id"]:
        raise ApiError(404, "NOT_FOUND", "No such row on this form.")
    audit(db, identity, "form_entry.delete", "form_entry", entry_id, entry_dict(entry), None)
    if entry.smarttt_synced_at is not None and entry.smarttt_lecturer_id is not None:
        entry.lecturer_id = None
        entry.lecturer = None
        entry.lecture_hours = entry.practical_hours = entry.cf_hours = None
        entry.entered_by_account_id = identity.account_id
        entry.entered_by_name = identity.actor
        entry.entered_at = utcnow()
    else:
        db.delete(entry)
    db.commit()


def submit(
    db: Session,
    generator: GeneratorClient,
    identity: Identity,
    department_code: str,
    term_id: str | None,
    smarttt: SmartttClient | None = None,
) -> dict[str, Any]:
    """
    The COD submits the form, which publishes it: each allocated class goes to
    SMARTTT (lecturers' timetables, Smart Attendance), once SMARTTT has the
    Director's approved timetable. SMARTTT re-checks clashes across every
    department; a class it refuses, or one it couldn't get (SMARTTT down),
    shows why, and “Publish again” retries.
    """
    ctx = context(generator, identity, department_code, term_id)
    _require_cod(ctx)
    _require_open(db, ctx)
    current = board(db, generator, identity, department_code, ctx.term["id"])
    unnumbered = sorted(
        {
            r["entry"]["lecturer"]
            for r in current["rows"]
            if r["in_timetable"] and r["entry"] and r["smarttt"]["state"] == smarttt_sync.NO_STAFF_NUMBER
        }
    )
    if unnumbered:
        raise ApiError(
            409,
            "NO_STAFF_NUMBER",
            f"Add the staff number of {', '.join(unnumbered[:5])} on the Lecturers tab, "
            "so SMARTTT knows who they are.",
        )
    blocking = [r for r in current["rows"] if r["problems"]]
    if blocking:
        raise ApiError(
            409,
            "FORM_HAS_PROBLEMS",
            f"{len(blocking)} classes have a lecturer clash or too many hours. Fix them before submitting.",
            {"keys": [r["key"] for r in blocking]},
        )
    submission = FormSubmission(
        generator_term_id=ctx.term["id"],
        department_code=_code(ctx),
        submitted_by_account_id=identity.account_id,
        submitted_by_name=identity.actor,
        entry_count=current["summary"]["classes"],
        allocated_count=current["summary"]["allocated"],
    )
    db.add(submission)
    db.flush()
    audit(db, identity, "form.submit", "department", _code(ctx), None, current["summary"])
    db.commit()
    if smarttt is not None:
        _publish(db, smarttt, ctx)
    return board(db, generator, identity, department_code, ctx.term["id"])


def reopen(
    db: Session, generator: GeneratorClient, identity: Identity, department_code: str, term_id: str | None
) -> dict[str, Any]:
    ctx = context(generator, identity, department_code, term_id)
    _require_cod(ctx)
    submission = current_submission(db, ctx.term["id"], _code(ctx))
    if submission is None:
        raise ApiError(409, "NOT_SUBMITTED", "This allocation hasn't been submitted.")
    submission.reopened_at = utcnow()
    submission.reopened_by_name = identity.actor
    audit(db, identity, "form.reopen", "department", _code(ctx), None, None)
    db.commit()
    return board(db, generator, identity, department_code, ctx.term["id"])


def progress(
    db: Session, generator: GeneratorClient, identity: Identity, term_id: str | None
) -> dict[str, Any]:
    """Every department's form at a glance, for the Directorate (others see their own)."""
    term = pick_term(generator, term_id)
    sections = list(generator.sections(term["id"]).get("sections") or [])
    entries = _term_entries(db, term["id"])
    allocated = {e.key for e in entries if e.lecturer_id}
    by_department: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for s in sections:
        if s.get("department"):
            by_department[compact(s["department"]["code"])].append(s)
    rows = []
    for d in visible_departments(identity, sections):
        code = compact(d["code"])
        own = by_department.get(code, [])
        submission = current_submission(db, term["id"], code)
        rows.append(
            {
                **d,
                "classes": len(own),
                "allocated": sum(1 for s in own if s["key"] in allocated),
                "submitted_at": submission.submitted_at.isoformat() if submission else None,
                "submitted_by": submission.submitted_by_name if submission else None,
            }
        )
    return {"term": term, "departments": rows}


# -- bulk entry -------------------------------------------------------------------------------

_KIND = re.compile(r"\((FT|PT)\)\s*$", re.IGNORECASE)
_TITLE = re.compile(r"^(DR|PROF|MR|MRS|MS|MISS|ENG|REV)\.?\s+", re.IGNORECASE)


def split_name(raw: str) -> tuple[str, str, EmploymentType]:
    """'Dr. Joseph Omollo (PT)' -> ('Dr.', 'Joseph Omollo', part time), as the Word form writes lecturers."""
    text = raw.strip()
    kind = EmploymentType.FULL_TIME
    match = _KIND.search(text)
    if match:
        kind = EmploymentType.PART_TIME if match.group(1).upper() == "PT" else EmploymentType.FULL_TIME
        text = text[: match.start()].strip()
    title = ""
    match = _TITLE.match(text)
    if match:
        title = match.group(1).capitalize() + "."
        text = text[match.end() :].strip()
    return title, text, kind


def _clean(row: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in row.items():
        k = re.sub(r"[^a-z0-9]+", "_", str(key).strip().lower()).strip("_")
        v = str(value).strip() if value is not None else ""
        if v:
            out[k] = v
    return out


def _number(value: str | None, what: str) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(str(value).replace(",", "."))
    except ValueError as exc:
        raise ValueError(f"{what} '{value}' is not a number") from exc
    if not 0 <= number <= 500:
        raise ValueError(f"{what} must be between 0 and 500")
    return number


def bulk_lecturers(
    db: Session,
    generator: GeneratorClient,
    identity: Identity,
    department_code: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    ctx = context(generator, identity, department_code, None)
    _require_allocate(ctx)
    created = updated = 0
    errors: list[dict[str, Any]] = []
    # Each lecturer once per file: a repeat is a mistake (two people given one
    # staff number), never a reason to overwrite the earlier row.
    staff_rows: dict[str, tuple[int, str]] = {}
    lecturer_rows: dict[uuid.UUID, int] = {}
    for line, raw in enumerate(rows, start=1):
        r = _clean(raw)
        try:
            name_cell = r.get("full_name") or r.get("name") or r.get("lecturer")
            if not name_cell:
                raise ValueError("name is required")
            title, name, kind = split_name(name_cell)
            kind_cell = (r.get("employment") or r.get("ft_pt") or "").upper()
            if kind_cell:
                kind = EmploymentType.PART_TIME if kind_cell.startswith("P") else EmploymentType.FULL_TIME
            fields: dict[str, Any] = {
                "title": r.get("title", title),
                "full_name": name,
                "staff_number": r.get("staff_number") or r.get("staff_no"),
                "employment_type": kind.value,
                "phone": r.get("phone") or r.get("phone_no") or "",
                "email": r.get("email") or "",
            }
            if r.get("max_hours") or r.get("max_weekly_hours"):
                fields["max_weekly_hours"] = (
                    int(float(r.get("max_hours") or r.get("max_weekly_hours") or 0)) or None
                )
            staff = (fields["staff_number"] or "").strip().upper()
            if staff in staff_rows:
                earlier, earlier_name = staff_rows[staff]
                raise ValueError(
                    f"staff number {staff} is also on row {earlier} ({earlier_name}); "
                    "each lecturer needs their own staff number"
                )
            existing = _find_lecturer(db, _code(ctx), staff or None, name)
            if existing is not None and existing.id in lecturer_rows:
                raise ValueError(f"{name} is also on row {lecturer_rows[existing.id]}")
            if existing is not None and staff and not same_name(existing.full_name, name):
                raise ValueError(
                    f"staff number {staff} is already on the list as {existing.full_name}; "
                    "check the staff number, or change the name on their own record"
                )
            if staff:
                staff_rows[staff] = (line, name_cell)
            if existing is not None:
                lecturer_rows[existing.id] = line
                before = lecturer_dict(existing)
                _apply_lecturer(db, existing, {k: v for k, v in fields.items() if v not in (None, "")})
                db.flush()
                audit(
                    db,
                    identity,
                    "lecturer.update",
                    "lecturer",
                    str(existing.id),
                    before,
                    lecturer_dict(existing),
                )
                updated += 1
            else:
                lecturer_rows[create_lecturer(db, identity, ctx, fields, commit=False).id] = line
                created += 1
            db.flush()
        except (ValueError, ApiError) as exc:
            errors.append({"line": line, "message": getattr(exc, "message", None) or str(exc)})
    db.commit()
    return {"created": created, "updated": updated, "errors": errors[:200], "error_count": len(errors)}


def _find_lecturer(db: Session, department_code: str, staff_number: str | None, name: str) -> Lecturer | None:
    if staff_number:
        found = db.scalar(
            select(Lecturer).where(
                Lecturer.department_code == department_code,
                func.upper(Lecturer.staff_number) == staff_number.strip().upper(),
            )
        )
        if found is not None:
            return found
    # Same name but another staff number: a different person who shares the name.
    return next(
        (
            lec
            for lec in department_lecturers(db, department_code)
            if same_name(lec.full_name, name) and not (staff_number and lec.staff_number)
        ),
        None,
    )


def same_name(a: str, b: str) -> bool:
    """'James Ng'ang'a' and 'james  nganga' are one name: letters only, any case."""
    return re.sub(r"[^a-z]", "", a.lower()) == re.sub(r"[^a-z]", "", b.lower())


def bulk_entries(
    db: Session,
    generator: GeneratorClient,
    identity: Identity,
    department_code: str,
    term_id: str | None,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Rows pasted from the Word or Excel allocation form: Course code, Group,
    Course title, L, P, CF, Lecturer ("Dr. Joseph Omollo (PT)"). A lecturer
    not on the department's list yet is added to it.
    """
    ctx = context(generator, identity, department_code, term_id)
    _require_allocate(ctx)
    _require_open(db, ctx)
    created = updated = lecturers_added = 0
    errors: list[dict[str, Any]] = []
    class_rows: dict[str, int] = {}  # each class once per file; a repeat would overwrite the earlier row
    for line, raw in enumerate(rows, start=1):
        r = _clean(raw)
        try:
            unit = r.get("course_code") or r.get("unit_code") or r.get("code")
            if not unit:
                raise ValueError("course code is required")
            # "COSC 103 Group A" / "COSC 103 GR A" in one cell, as on the Word form.
            group = r.get("group") or ""
            match = re.search(r"\s+(?:GROUP|GRP|GR\.?)\s*([A-Z]\d?)\s*$", unit, re.IGNORECASE)
            if match and not group:
                group = f"GR {match.group(1).upper()}"
                unit = unit[: match.start()].strip()
            elif group and not group.upper().startswith("GR"):
                group = f"GR {group.upper()}"
            key = form_key(unit, group)
            if key in class_rows:
                raise ValueError(f"{unit} {group}".strip() + f" is also on row {class_rows[key]}")
            class_rows[key] = line
            lecturer_id = None
            name_cell = r.get("lecturer")
            if name_cell:
                title, name, kind = split_name(name_cell)
                lecturer = _find_lecturer(db, _code(ctx), r.get("staff_number"), name)
                if lecturer is None:
                    lecturer = create_lecturer(
                        db,
                        identity,
                        ctx,
                        {
                            "title": title,
                            "full_name": name,
                            "employment_type": kind.value,
                            "phone": r.get("phone_no") or r.get("phone") or "",
                        },
                        commit=False,
                    )
                    lecturers_added += 1
                lecturer_id = str(lecturer.id)
            existed = db.scalar(
                select(FormEntry).where(
                    FormEntry.generator_term_id == ctx.term["id"], FormEntry.key == form_key(unit, group)
                )
            )
            fields = {
                "unit_code": unit,
                "group_label": group,
                "unit_title": r.get("course_title") or r.get("unit_title") or r.get("title"),
                "lecturer_id": lecturer_id,
                "lecture_hours": _number(r.get("l") or r.get("lecture_hours"), "L"),
                "practical_hours": _number(r.get("p") or r.get("practical_hours"), "P"),
                "cf_hours": _number(r.get("cf") or r.get("cf_hours"), "CF"),
            }
            # Hours left blank on a pasted row keep what was entered before.
            fields = {k: v for k, v in fields.items() if v is not None or not k.endswith("_hours")}
            save_entry(
                db, generator, identity, department_code, ctx.term["id"], fields, ctx=ctx, commit=False
            )
            if existed is None:
                created += 1
            else:
                updated += 1
        except (ValueError, ApiError) as exc:
            errors.append({"line": line, "message": getattr(exc, "message", None) or str(exc)})
    db.commit()
    return {
        "created": created,
        "updated": updated,
        "lecturers_added": lecturers_added,
        "errors": errors[:200],
        "error_count": len(errors),
    }


# -- SMARTTT --------------------------------------------------------------------------------


def _publish(db: Session, smarttt: SmartttClient, ctx: Context) -> None:
    """Sends the department's classes SMARTTT doesn't have as on the form; refusals stay on the class."""
    code = _code(ctx)
    sections = {
        s["key"]: s for s in ctx.sections if s.get("department") and compact(s["department"]["code"]) == code
    }
    for entry in _term_entries(db, ctx.term["id"]):
        if entry.department_code == code and entry.key in sections:
            smarttt_sync.push(smarttt, entry, ctx.smarttt_target(sections[entry.key]))
    db.commit()


def publish_again(
    db: Session,
    generator: GeneratorClient,
    smarttt: SmartttClient,
    identity: Identity,
    department_code: str,
    term_id: str | None,
) -> dict[str, Any]:
    """
    “Publish again”: the submitted form's classes SMARTTT didn't take (it was
    down, said no, or got the Director's timetable only since).
    """
    ctx = context(generator, identity, department_code, term_id)
    _require_cod(ctx)
    if current_submission(db, ctx.term["id"], _code(ctx)) is None:
        raise ApiError(409, "NOT_SUBMITTED", "Submit the form to publish it.")
    if not ctx.term.get("smarttt_term_id"):
        raise ApiError(409, "NOT_IN_SMARTTT", "This term is only in the Timetable Generator, not in SMARTTT.")
    if not ctx.in_smarttt:
        raise ApiError(
            409,
            "NOT_IN_SMARTTT",
            "SMARTTT doesn't have the Director's approved timetable yet; nothing can be sent.",
        )
    _publish(db, smarttt, ctx)
    return board(db, generator, identity, department_code, ctx.term["id"])


def sort_meetings(meetings: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(meetings, key=lambda m: (DAY_ORDER.get(m["day_of_week"], 9), m["start_time"]))
