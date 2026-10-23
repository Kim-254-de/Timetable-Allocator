"""
What departments enter and publish to the Director.

For a term of the Timetable Generator, each department enters its courses
(cohorts, which become class rows), its units with the courses that take
them, and each unit's groups: the whole class, or a split into groups A, B,
C..., each with its courses, students, lecturer and the form's L/P/CF hours.
A unit taught to another department's students is entered by the department
that owns it, which picks the other department's courses from the shared list.

The COD publishes the department's list once nothing is missing; that locks
it until the COD reopens it. The Generator imports what is published, gives
every group a day, time and room, and the Director publishes the timetable.
There is no clash check here: times don't exist until the Generator solves.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import ROLE_COD, Identity
from app.clients.generator import GeneratorClient
from app.clients.smarttt import SmartttClient
from app.errors import ApiError
from app.models import (
    Course,
    DepartmentPublication,
    Lecturer,
    Unit,
    UnitCourse,
    UnitGroup,
    UnitGroupMember,
    utcnow,
)
from app.services.allocation import audit
from app.services.departments import (
    Context,
    all_departments,
    compact,
    context,
    current_publication,
    last_publication,
    pick_term,
    require_cod,
    require_enter,
    require_open,
    visible_departments,
)
from app.services.lecturers import department_lecturers, display_name, get_lecturer, lecturer_dict, person
from app.services.timeutil import DAY_ORDER

ROOM_TYPES = {"lecture_hall": "Lecture hall", "lab": "Lab", "seminar": "Seminar room"}


def class_key(unit_code: str, group_label: str) -> str:
    """'COSC 103', 'GR A' -> 'COSC103-GRA'; a whole class -> 'COSC103-MAIN', as the Generator keys it."""
    return f"{compact(unit_code)}-{compact(group_label) or 'MAIN'}"


def _num(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _dec(value: float | None) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def _uuid(value: str, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except ValueError as exc:
        raise ApiError(404, "NOT_FOUND", f"No such {what}.") from exc


# -- reading ----------------------------------------------------------------------------------


def term_courses(db: Session, term_id: str) -> list[Course]:
    return list(
        db.scalars(
            select(Course)
            .where(Course.generator_term_id == term_id)
            .order_by(Course.programme, Course.year, Course.semester, Course.sub_class)
        )
    )


def term_units(db: Session, term_id: str) -> list[Unit]:
    return list(db.scalars(select(Unit).where(Unit.generator_term_id == term_id).order_by(Unit.code_key)))


def course_dict(c: Course) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "department_code": c.department_code,
        "programme": c.programme,
        "year": c.year,
        "semester": c.semester,
        "sub_class": c.sub_class,
        "label": c.label,
        "students": c.students,
    }


def member_students(member: UnitGroupMember, courses: dict[uuid.UUID, Course]) -> int:
    """A member's students: as given when the course is split, else the whole course."""
    if member.students is not None:
        return member.students
    course = courses.get(member.course_id)
    return course.students if course else 0


def group_students(group: UnitGroup, courses: dict[uuid.UUID, Course]) -> int:
    return sum(member_students(m, courses) for m in group.members)


def signature(unit: Unit, courses: dict[uuid.UUID, Course]) -> str:
    """Everything the Director gets about a unit, hashed: a unit that changed since publishing differs."""

    def label(course_id: uuid.UUID) -> str:
        course = courses.get(course_id)
        return course.label if course else str(course_id)

    data = {
        "code": unit.code,
        "title": unit.title,
        "weekly_hours": unit.weekly_hours,
        "class_length": unit.class_length,
        "room_type": unit.room_type,
        "courses": sorted(label(c.course_id) for c in unit.courses),
        "groups": [
            {
                "label": g.label,
                "members": sorted((label(m.course_id), m.students or 0) for m in g.members),
                "lecturer": g.lecturer.staff_number if g.lecturer else None,
                "hours": [str(g.lecture_hours), str(g.practical_hours), str(g.cf_hours)],
            }
            for g in sorted(unit.groups, key=lambda g: g.label)
        ],
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def weekly_load(units: list[Unit]) -> dict[str, float]:
    """Each person's teaching hours a week, from every department's groups (one person = one staff number)."""
    load: dict[str, float] = defaultdict(float)
    for u in units:
        for g in u.groups:
            if g.lecturer is not None:
                load[person(g.lecturer)] += u.weekly_hours
    return load


def problems(
    ctx_code: str, own_units: list[Unit], all_units: list[Unit], courses: dict[uuid.UUID, Course]
) -> list[dict[str, Any]]:
    """What must be fixed before the COD can publish. Each: {code, message, unit_id?}."""
    found: list[dict[str, Any]] = []

    def add(code: str, message: str, unit: Unit | None = None) -> None:
        found.append({"code": code, "message": message, "unit_id": str(unit.id) if unit else None})

    if not own_units:
        add("no_units", "Add at least one unit.")
    lecturers: dict[uuid.UUID, Lecturer] = {}
    for u in own_units:
        taking = {c.course_id for c in u.courses}
        if not taking:
            add("no_courses", f"{u.code} has no courses taking it.", u)
        if not u.groups:
            add("no_groups", f"{u.code} has no group.", u)
        in_groups: dict[uuid.UUID, list[UnitGroupMember]] = defaultdict(list)
        for g in u.groups:
            name = f"{u.code} {g.label}".strip()
            if g.lecturer is None:
                add("no_lecturer", f"{name} has no lecturer.", u)
            else:
                lecturers[g.lecturer.id] = g.lecturer
            if not g.members:
                add("empty_group", f"{name} has no courses in it.", u)
            for m in g.members:
                in_groups[m.course_id].append(m)
        for course_id in taking:
            course = courses.get(course_id)
            if course is None:
                continue
            members = in_groups.get(course_id) or []
            if not members:
                if u.groups:
                    add(
                        "course_not_in_group",
                        f"{course.label} takes {u.code} but is in none of its groups.",
                        u,
                    )
                continue
            total = sum(member_students(m, courses) for m in members)
            if total != course.students:
                add(
                    "split_total",
                    f"{course.label} has {course.students} students, but {u.code}'s groups "
                    f"have {total} of them.",
                    u,
                )
    load = weekly_load(all_units)
    for lec in sorted(lecturers.values(), key=lambda lec: lec.full_name):
        if not lec.staff_number:
            add("no_staff_number", f"Add {lec.full_name}'s staff number on the Lecturers tab.")
        hours = load.get(person(lec), 0.0)
        if lec.max_weekly_hours and hours > lec.max_weekly_hours:
            add(
                "over_hours",
                f"{lec.full_name} would teach {hours:g} hours a week across all departments; "
                f"the limit is {lec.max_weekly_hours}.",
            )
    return found


def _times(generator: GeneratorClient, ctx: Context) -> dict[str, Any]:
    """When and where each class meets, once the Director has published (read from the Generator)."""
    if ctx.term.get("published_version") is None:
        return {"published_version": None, "classes": {}, "error": None}
    try:
        data = generator.times(ctx.term_id)
    except ApiError as exc:
        return {"published_version": None, "classes": {}, "error": exc.message}
    return {
        "published_version": data.get("published_version"),
        "classes": dict(data.get("classes") or {}),
        "error": None,
    }


def _sort_meetings(meetings: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(meetings, key=lambda m: (DAY_ORDER.get(m["day_of_week"], 9), m["start_time"]))


def unit_dict(
    u: Unit,
    courses: dict[uuid.UUID, Course],
    times: dict[str, list[dict[str, str]]],
    ever_published: bool,
) -> dict[str, Any]:
    def course(course_id: uuid.UUID) -> dict[str, Any]:
        c = courses.get(course_id)
        if c is None:
            return {"id": str(course_id), "label": "?", "department_code": None, "students": 0}
        return {
            "id": str(c.id),
            "label": c.label,
            "department_code": c.department_code,
            "students": c.students,
        }

    taking = sorted((course(c.course_id) for c in u.courses), key=lambda c: c["label"])
    return {
        "id": str(u.id),
        "department_code": u.department_code,
        "code": u.code,
        "title": u.title,
        "weekly_hours": u.weekly_hours,
        "class_length": u.class_length,
        "room_type": u.room_type,
        "courses": taking,
        "servicing": any(c["department_code"] and c["department_code"] != u.department_code for c in taking),
        "changed_since_published": ever_published and u.published_signature != signature(u, courses),
        "groups": [
            {
                "id": str(g.id),
                "key": class_key(u.code, g.label),
                "label": g.label,
                "members": sorted(
                    ({**course(m.course_id), "given_students": m.students} for m in g.members),
                    key=lambda c: c["label"],
                ),
                "students": group_students(g, courses),
                "lecturer_id": str(g.lecturer_id) if g.lecturer_id else None,
                "lecturer": display_name(g.lecturer) if g.lecturer else None,
                "lecture_hours": _num(g.lecture_hours),
                "practical_hours": _num(g.practical_hours),
                "cf_hours": _num(g.cf_hours),
                "meetings": _sort_meetings(times.get(class_key(u.code, g.label)) or []),
            }
            for g in u.groups
        ],
    }


def publication_dict(p: DepartmentPublication | None) -> dict[str, Any] | None:
    if p is None:
        return None
    return {
        "published_by": p.published_by_name,
        "published_at": p.published_at.isoformat(),
        "unit_count": p.unit_count,
        "group_count": p.group_count,
        "reopened_at": p.reopened_at.isoformat() if p.reopened_at else None,
        "reopened_by": p.reopened_by_name,
    }


def board(
    db: Session,
    generator: GeneratorClient,
    smarttt: SmartttClient,
    identity: Identity,
    department_code: str,
    term_id: str | None,
) -> dict[str, Any]:
    """Everything on a department's page: courses, units and groups, lecturers, what blocks publishing."""
    ctx = context(generator, smarttt, identity, department_code, term_id)
    courses = term_courses(db, ctx.term_id)
    by_id = {c.id: c for c in courses}
    units = term_units(db, ctx.term_id)
    own_units = [u for u in units if u.department_code == ctx.code]
    standing = current_publication(db, ctx.term_id, ctx.code)
    last = last_publication(db, ctx.term_id, ctx.code)
    times = _times(generator, ctx)
    used_by: dict[uuid.UUID, list[str]] = defaultdict(list)
    for u in units:
        for c in u.courses:
            used_by[c.course_id].append(u.code)
    load = weekly_load(units)
    own_groups: dict[uuid.UUID, int] = defaultdict(int)
    for u in own_units:
        for g in u.groups:
            if g.lecturer_id:
                own_groups[g.lecturer_id] += 1
    show_contacts = ctx.role is not None or identity.timetabling_office
    found = problems(ctx.code, own_units, units, by_id)
    unit_rows = [unit_dict(u, by_id, times["classes"], last is not None) for u in own_units]
    return {
        "term": ctx.term,
        "department": ctx.department,
        "role": ctx.role,
        "can_edit": ctx.role is not None and standing is None,
        "can_publish": ctx.role == ROLE_COD,
        "publication": publication_dict(standing or last),
        "published": standing is not None,
        "courses": [
            {**course_dict(c), "used_by": sorted(used_by.get(c.id, []))}
            for c in courses
            if c.department_code == ctx.code
        ],
        # Every other department's courses, read-only, for units this department services.
        "other_courses": [course_dict(c) for c in courses if c.department_code != ctx.code],
        "units": unit_rows,
        "lecturers": [
            {
                **lecturer_dict(lec, show_contacts),
                "display": display_name(lec),
                "groups": own_groups.get(lec.id, 0),
                # Across every department this person teaches for.
                "weekly_hours": load.get(person(lec), 0.0),
            }
            for lec in department_lecturers(db, ctx.code)
        ],
        "problems": found,
        "times": {"published_version": times["published_version"], "error": times["error"]},
        "summary": {
            "courses": sum(1 for c in courses if c.department_code == ctx.code),
            "units": len(own_units),
            "groups": sum(len(u.groups) for u in own_units),
            "with_lecturer": sum(1 for u in own_units for g in u.groups if g.lecturer_id),
            "changed": sum(1 for u in unit_rows if u["changed_since_published"]),
            "problems": len(found),
        },
    }


# -- courses ---------------------------------------------------------------------------------


def _get_course(db: Session, ctx: Context, course_id: str) -> Course:
    course = db.get(Course, _uuid(course_id, "course"))
    if course is None or course.generator_term_id != ctx.term_id:
        raise ApiError(404, "NOT_FOUND", "No such course.")
    if course.department_code != ctx.code:
        raise ApiError(
            403, "FORBIDDEN", f"{course.label} is {course.department_code}'s course; only they edit it."
        )
    return course


def _apply_course(db: Session, ctx: Context, course: Course, fields: dict[str, Any]) -> None:
    """Checks everything first, so a refused change leaves the course as it was."""
    values: dict[str, Any] = {
        k: getattr(course, k) for k in ("programme", "year", "semester", "sub_class", "students")
    }
    for key in values:
        if fields.get(key) is not None:
            value = fields[key]
            values[key] = " ".join(str(value).split()).upper() if key in ("programme", "sub_class") else value
    if not values["programme"]:
        raise ApiError(422, "VALIDATION_ERROR", "Give the programme.")
    clash = db.scalar(
        select(Course).where(
            Course.generator_term_id == ctx.term_id,
            Course.programme == values["programme"],
            Course.year == values["year"],
            Course.semester == values["semester"],
            Course.sub_class == values["sub_class"],
            Course.id != course.id,
        )
    )
    if clash is not None:
        owner = "your department" if clash.department_code == ctx.code else clash.department_code
        raise ApiError(409, "COURSE_TAKEN", f"{clash.label} is already entered by {owner}.")
    for key, value in values.items():
        setattr(course, key, value)


def create_course(
    db: Session, identity: Identity, ctx: Context, fields: dict[str, Any], commit: bool = True
) -> Course:
    require_enter(ctx)
    require_open(db, ctx)
    course = Course(generator_term_id=ctx.term_id, department_code=ctx.code, sub_class="")
    _apply_course(db, ctx, course, fields)
    db.add(course)
    db.flush()
    audit(db, identity, "course.create", "course", str(course.id), None, course_dict(course))
    if commit:
        db.commit()
    return course


def update_course(
    db: Session, identity: Identity, ctx: Context, course_id: str, fields: dict[str, Any], commit: bool = True
) -> Course:
    require_enter(ctx)
    require_open(db, ctx)
    course = _get_course(db, ctx, course_id)
    before = course_dict(course)
    _apply_course(db, ctx, course, fields)
    db.flush()
    audit(db, identity, "course.update", "course", str(course.id), before, course_dict(course))
    if commit:
        db.commit()
    return course


def delete_course(db: Session, identity: Identity, ctx: Context, course_id: str) -> None:
    require_enter(ctx)
    require_open(db, ctx)
    course = _get_course(db, ctx, course_id)
    using = list(
        db.scalars(
            select(Unit)
            .join(UnitCourse, UnitCourse.unit_id == Unit.id)
            .where(UnitCourse.course_id == course.id)
        )
    )
    if using:
        names = ", ".join(
            u.code if u.department_code == ctx.code else f"{u.code} ({u.department_code})" for u in using[:5]
        )
        raise ApiError(409, "IN_USE", f"{course.label} takes {names}. Remove it from those units first.")
    audit(db, identity, "course.delete", "course", str(course.id), course_dict(course), None)
    db.delete(course)
    db.commit()


# -- units -----------------------------------------------------------------------------------


def _get_unit(db: Session, ctx: Context, unit_id: str) -> Unit:
    unit = db.get(Unit, _uuid(unit_id, "unit"))
    if unit is None or unit.generator_term_id != ctx.term_id or unit.department_code != ctx.code:
        raise ApiError(404, "NOT_FOUND", "No such unit in this department.")
    return unit


def _term_course_ids(db: Session, ctx: Context, ids: list[str]) -> list[uuid.UUID]:
    wanted = [_uuid(i, "course") for i in dict.fromkeys(ids)]
    found = set(
        db.scalars(select(Course.id).where(Course.generator_term_id == ctx.term_id, Course.id.in_(wanted)))
    )
    if len(found) != len(wanted):
        raise ApiError(422, "VALIDATION_ERROR", "A course chosen isn't in this term.")
    return wanted


def _whole_class(unit: Unit) -> UnitGroup | None:
    """The unit's only group when it isn't split."""
    return unit.groups[0] if len(unit.groups) == 1 and unit.groups[0].label == "" else None


def _set_unit_courses(unit: Unit, course_ids: list[uuid.UUID]) -> None:
    keep = set(course_ids)
    unit.courses = [c for c in unit.courses if c.course_id in keep] + [
        UnitCourse(course_id=i) for i in course_ids if i not in {c.course_id for c in unit.courses}
    ]
    for g in unit.groups:
        g.members = [m for m in g.members if m.course_id in keep]
    whole = _whole_class(unit)
    if whole is not None:
        have = {m.course_id for m in whole.members}
        whole.members.extend(UnitGroupMember(course_id=i) for i in course_ids if i not in have)


def _apply_unit(db: Session, ctx: Context, unit: Unit, fields: dict[str, Any]) -> None:
    """Checks everything first, so a refused change leaves the unit as it was."""
    values: dict[str, Any] = {
        k: getattr(unit, k) for k in ("code", "title", "weekly_hours", "class_length", "room_type")
    }
    for key in values:
        if fields.get(key) is not None:
            values[key] = " ".join(str(fields[key]).split()) if key in ("code", "title") else fields[key]
    if not values["code"] or not values["title"]:
        raise ApiError(422, "VALIDATION_ERROR", "Give the unit's code and title.")
    if not values["weekly_hours"] or not values["class_length"]:
        raise ApiError(422, "VALIDATION_ERROR", "Give the unit's hours per week and class length.")
    if values["room_type"] not in ROOM_TYPES:
        raise ApiError(422, "VALIDATION_ERROR", "Room type must be Lecture hall, Lab or Seminar room.")
    if values["class_length"] > values["weekly_hours"]:
        raise ApiError(422, "VALIDATION_ERROR", "A class can't be longer than the unit's hours per week.")
    values["code"] = values["code"].upper()
    code_key = compact(values["code"])
    clash = db.scalar(
        select(Unit).where(
            Unit.generator_term_id == ctx.term_id, Unit.code_key == code_key, Unit.id != unit.id
        )
    )
    if clash is not None:
        owner = "your department" if clash.department_code == ctx.code else clash.department_code
        raise ApiError(409, "UNIT_TAKEN", f"{clash.code} is already entered by {owner}.")
    for key, value in values.items():
        setattr(unit, key, value)
    unit.code_key = code_key


def _unit_audit(unit: Unit) -> dict[str, Any]:
    return {
        "code": unit.code,
        "title": unit.title,
        "weekly_hours": unit.weekly_hours,
        "class_length": unit.class_length,
        "room_type": unit.room_type,
        "courses": sorted(str(c.course_id) for c in unit.courses),
    }


def create_unit(
    db: Session, identity: Identity, ctx: Context, fields: dict[str, Any], commit: bool = True
) -> Unit:
    """A new unit is one whole class of all the courses taking it, until the department splits it."""
    require_enter(ctx)
    require_open(db, ctx)
    unit = Unit(
        generator_term_id=ctx.term_id,
        department_code=ctx.code,
        room_type="lecture_hall",
        entered_by_name=identity.actor,
    )
    course_ids = _term_course_ids(db, ctx, list(fields.get("course_ids") or []))
    if not course_ids:
        raise ApiError(422, "VALIDATION_ERROR", "Choose the courses that take the unit.")
    _apply_unit(db, ctx, unit, fields)
    unit.courses = [UnitCourse(course_id=i) for i in course_ids]
    unit.groups = [UnitGroup(label="", members=[UnitGroupMember(course_id=i) for i in course_ids])]
    db.add(unit)
    db.flush()
    audit(db, identity, "unit.create", "unit", str(unit.id), None, _unit_audit(unit))
    if commit:
        db.commit()
    return unit


def update_unit(
    db: Session, identity: Identity, ctx: Context, unit_id: str, fields: dict[str, Any], commit: bool = True
) -> Unit:
    require_enter(ctx)
    require_open(db, ctx)
    unit = _get_unit(db, ctx, unit_id)
    before = _unit_audit(unit)
    course_ids = _term_course_ids(db, ctx, list(fields["course_ids"])) if fields.get("course_ids") else None
    _apply_unit(db, ctx, unit, fields)
    if course_ids is not None:
        _set_unit_courses(unit, course_ids)
    unit.entered_by_name = identity.actor
    db.flush()
    audit(db, identity, "unit.update", "unit", str(unit.id), before, _unit_audit(unit))
    if commit:
        db.commit()
    return unit


def delete_unit(db: Session, identity: Identity, ctx: Context, unit_id: str) -> None:
    require_enter(ctx)
    require_open(db, ctx)
    unit = _get_unit(db, ctx, unit_id)
    audit(db, identity, "unit.delete", "unit", str(unit.id), _unit_audit(unit), None)
    db.delete(unit)
    db.commit()


# -- groups ----------------------------------------------------------------------------------


def group_label(raw: str | None) -> str:
    """'a', 'Group A', 'GR A' -> 'GR A'; blank -> '' (the whole class)."""
    text = " ".join((raw or "").split()).upper()
    for prefix in ("GROUP", "GRP", "GR."):
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
    if text.startswith("GR ") or text == "GR":
        text = text[2:].strip()
    return f"GR {text}" if text else ""


def _lecturer_for(db: Session, ctx: Context, lecturer_id: str | None) -> Lecturer | None:
    if not lecturer_id:
        return None
    lecturer = get_lecturer(db, lecturer_id)
    if lecturer.department_code != ctx.code:
        raise ApiError(403, "FORBIDDEN", "That lecturer is on another department's list.")
    if not lecturer.active:
        raise ApiError(422, "VALIDATION_ERROR", f"{lecturer.full_name} is marked inactive.")
    return lecturer


def _group_audit(unit: Unit) -> list[dict[str, Any]]:
    return [
        {
            "label": g.label,
            "members": sorted([str(m.course_id), m.students] for m in g.members),
            "lecturer_id": str(g.lecturer_id) if g.lecturer_id else None,
            "hours": [_num(g.lecture_hours), _num(g.practical_hours), _num(g.cf_hours)],
        }
        for g in unit.groups
    ]


def set_groups(
    db: Session,
    identity: Identity,
    ctx: Context,
    unit_id: str,
    groups: list[dict[str, Any]],
    commit: bool = True,
) -> Unit:
    """
    The unit's classes, all at once: one whole class, or groups A, B, C...
    Each group's courses must take the unit; a course split between groups
    gives each group's share of its students. A group kept by label keeps its
    lecturer and hours unless new ones are given.
    """
    require_enter(ctx)
    require_open(db, ctx)
    unit = _get_unit(db, ctx, unit_id)
    if not groups:
        raise ApiError(422, "VALIDATION_ERROR", "A unit needs at least one group.")
    courses = {c.id: c for c in term_courses(db, ctx.term_id)}
    taking = {c.course_id for c in unit.courses}
    labels = [group_label(g.get("label")) for g in groups]
    if len(set(labels)) != len(labels):
        raise ApiError(422, "VALIDATION_ERROR", "Each group needs its own name.")
    if len(labels) > 1 and "" in labels:
        raise ApiError(422, "VALIDATION_ERROR", "When a unit is split, name every group (A, B, C...).")
    before = _group_audit(unit)
    # Every group is checked before any changes, so a refused split leaves the unit as it was.
    checked: list[tuple[str, dict[str, Any], list[tuple[uuid.UUID, int | None]], Lecturer | None]] = []
    for label, data in zip(labels, groups, strict=True):
        name = f"{unit.code} {label}".strip()
        members: list[tuple[uuid.UUID, int | None]] = []
        seen: set[uuid.UUID] = set()
        for m in data.get("members") or []:
            course_id = _uuid(m["course_id"], "course")
            if course_id not in taking:
                raise ApiError(422, "VALIDATION_ERROR", f"A course in {name} doesn't take {unit.code}.")
            if course_id in seen:
                raise ApiError(422, "VALIDATION_ERROR", f"{courses[course_id].label} is in {name} twice.")
            seen.add(course_id)
            students = m.get("students")
            if students is not None and not 1 <= students <= courses[course_id].students:
                raise ApiError(
                    422,
                    "VALIDATION_ERROR",
                    f"{name}: {courses[course_id].label} has {courses[course_id].students} students.",
                )
            members.append((course_id, students))
        if not members:
            raise ApiError(422, "VALIDATION_ERROR", f"Put at least one course in {name}.")
        lecturer = _lecturer_for(db, ctx, data.get("lecturer_id")) if "lecturer_id" in data else None
        checked.append((label, data, members, lecturer))
    existing = {g.label: g for g in unit.groups}
    new_groups: list[UnitGroup] = []
    for label, data, members, lecturer in checked:
        group = existing.get(label) or UnitGroup(label=label)
        group.members = [UnitGroupMember(course_id=c, students=s) for c, s in members]
        if "lecturer_id" in data:
            group.lecturer = lecturer
        for key in ("lecture_hours", "practical_hours", "cf_hours"):
            if key in data:
                setattr(group, key, _dec(data[key]))
        new_groups.append(group)
    unit.groups = new_groups
    unit.entered_by_name = identity.actor
    db.flush()
    audit(
        db, identity, "unit.groups", "unit", str(unit.id), {"groups": before}, {"groups": _group_audit(unit)}
    )
    if commit:
        db.commit()
    return unit


def update_group(
    db: Session, identity: Identity, ctx: Context, group_id: str, fields: dict[str, Any]
) -> UnitGroup:
    """A group's lecturer and L/P/CF hours."""
    require_enter(ctx)
    require_open(db, ctx)
    group = db.get(UnitGroup, _uuid(group_id, "group"))
    unit = db.get(Unit, group.unit_id) if group is not None else None
    if (
        group is None
        or unit is None
        or unit.generator_term_id != ctx.term_id
        or unit.department_code != ctx.code
    ):
        raise ApiError(404, "NOT_FOUND", "No such group in this department.")
    before = _group_audit(unit)
    if "lecturer_id" in fields:
        lecturer = _lecturer_for(db, ctx, fields["lecturer_id"])
        group.lecturer_id = lecturer.id if lecturer else None
        group.lecturer = lecturer
    for key in ("lecture_hours", "practical_hours", "cf_hours"):
        if key in fields:
            setattr(group, key, _dec(fields[key]))
    unit.entered_by_name = identity.actor
    db.flush()
    audit(
        db, identity, "unit.groups", "unit", str(unit.id), {"groups": before}, {"groups": _group_audit(unit)}
    )
    db.commit()
    return group


# -- publishing ------------------------------------------------------------------------------


def publish(
    db: Session,
    generator: GeneratorClient,
    smarttt: SmartttClient,
    identity: Identity,
    department_code: str,
    term_id: str | None,
) -> dict[str, Any]:
    """The COD sends the department's list to the Director; it stays locked until reopened."""
    ctx = context(generator, smarttt, identity, department_code, term_id)
    require_cod(ctx)
    require_open(db, ctx)
    courses = {c.id: c for c in term_courses(db, ctx.term_id)}
    units = term_units(db, ctx.term_id)
    own = [u for u in units if u.department_code == ctx.code]
    found = problems(ctx.code, own, units, courses)
    if found:
        raise ApiError(
            409,
            "NOT_READY",
            f"{len(found)} things must be fixed before publishing: {found[0]['message']}",
            {"problems": found[:50]},
        )
    for u in own:
        u.published_signature = signature(u, courses)
    publication = DepartmentPublication(
        generator_term_id=ctx.term_id,
        department_code=ctx.code,
        department_name=ctx.department["name"],
        published_by_account_id=identity.account_id,
        published_by_name=identity.actor,
        unit_count=len(own),
        group_count=sum(len(u.groups) for u in own),
    )
    db.add(publication)
    db.flush()
    audit(
        db,
        identity,
        "department.publish",
        "department",
        ctx.code,
        None,
        {"term": ctx.term_id, "units": publication.unit_count, "groups": publication.group_count},
    )
    db.commit()
    return board(db, generator, smarttt, identity, department_code, ctx.term_id)


def reopen(
    db: Session,
    generator: GeneratorClient,
    smarttt: SmartttClient,
    identity: Identity,
    department_code: str,
    term_id: str | None,
) -> dict[str, Any]:
    ctx = context(generator, smarttt, identity, department_code, term_id)
    require_cod(ctx)
    standing = current_publication(db, ctx.term_id, ctx.code)
    if standing is None:
        raise ApiError(409, "NOT_PUBLISHED", "This department's list hasn't been published.")
    standing.reopened_at = utcnow()
    standing.reopened_by_name = identity.actor
    audit(db, identity, "department.reopen", "department", ctx.code, None, {"term": ctx.term_id})
    db.commit()
    return board(db, generator, smarttt, identity, department_code, ctx.term_id)


def progress(
    db: Session, generator: GeneratorClient, smarttt: SmartttClient, identity: Identity, term_id: str | None
) -> dict[str, Any]:
    """Every department at a glance, for the Directorate (others see their own)."""
    term = pick_term(generator, term_id)
    units = term_units(db, str(term["id"]))
    by_department: dict[str, list[Unit]] = defaultdict(list)
    for u in units:
        by_department[u.department_code].append(u)
    rows = []
    for d in visible_departments(identity, smarttt):
        code = compact(d["code"])
        own = by_department.get(code, [])
        standing = current_publication(db, str(term["id"]), code)
        last = standing or last_publication(db, str(term["id"]), code)
        rows.append(
            {
                **d,
                "units": len(own),
                "groups": sum(len(u.groups) for u in own),
                "with_lecturer": sum(1 for u in own for g in u.groups if g.lecturer_id),
                "published": standing is not None,
                "publication": publication_dict(last),
            }
        )
    return {"term": term, "departments": rows}


# -- what the Generator reads -----------------------------------------------------------------


def submissions(db: Session, smarttt: SmartttClient, term_id: str) -> dict[str, Any]:
    """
    For the Director's "Import published departments": every published
    department with its courses, units and groups (lecturer by staff number),
    the courses those units take (any department's), and the departments
    that haven't published, with what changed in those that reopened.
    """
    courses = {c.id: c for c in term_courses(db, term_id)}
    units = term_units(db, term_id)
    by_department: dict[str, list[Unit]] = defaultdict(list)
    for u in units:
        by_department[u.department_code].append(u)
    latest: dict[str, DepartmentPublication] = {}
    for row in db.scalars(
        select(DepartmentPublication)
        .where(DepartmentPublication.generator_term_id == term_id)
        .order_by(DepartmentPublication.published_at)
    ):
        latest[row.department_code] = row
    try:
        known = {compact(d["code"]): d["name"] for d in all_departments(smarttt)}
    except ApiError:  # SMARTTT down: the departments that have entered anything
        known = {}
    for code in {*by_department, *latest}:
        known.setdefault(code, latest[code].department_name if code in latest else code)

    published: list[dict[str, Any]] = []
    waiting: list[dict[str, Any]] = []
    needed: set[uuid.UUID] = set()
    for code, name in sorted(known.items(), key=lambda kv: kv[1]):
        p = latest.get(code)
        own = by_department.get(code, [])
        if p is None or p.reopened_at is not None:
            waiting.append(
                {
                    "code": code,
                    "name": name,
                    "reopened_at": p.reopened_at.isoformat() if p and p.reopened_at else None,
                    "last_published_at": p.published_at.isoformat() if p else None,
                    "changed_units": sorted(
                        u.code
                        for u in own
                        if p is not None and u.published_signature != signature(u, courses)
                    ),
                }
            )
            continue
        for u in own:
            needed.update(c.course_id for c in u.courses)
        needed.update(c.id for c in courses.values() if c.department_code == code)
        published.append(
            {
                "code": code,
                "name": name,
                "published_at": p.published_at.isoformat(),
                "published_by": p.published_by_name,
                "units": [_submitted_unit(u, courses) for u in own],
            }
        )
    return {
        "term_id": term_id,
        "courses": [
            course_dict(courses[i]) for i in sorted(needed, key=lambda i: courses[i].label) if i in courses
        ],
        "published": published,
        "not_published": waiting,
    }


def _submitted_unit(u: Unit, courses: dict[uuid.UUID, Course]) -> dict[str, Any]:
    return {
        "id": str(u.id),
        "code": u.code,
        "title": u.title,
        "weekly_hours": u.weekly_hours,
        "class_length": u.class_length,
        "room_type": u.room_type,
        "course_ids": sorted(str(c.course_id) for c in u.courses),
        "groups": [
            {
                "id": str(g.id),
                "key": class_key(u.code, g.label),
                "label": g.label,
                "members": [
                    {"course_id": str(m.course_id), "students": member_students(m, courses)}
                    for m in g.members
                ],
                "students": group_students(g, courses),
                "lecturer": (
                    {
                        "staff_number": g.lecturer.staff_number,
                        "name": display_name(g.lecturer),
                        "employment_type": g.lecturer.employment_type.value,
                    }
                    if g.lecturer
                    else None
                ),
                "lecture_hours": _num(g.lecture_hours),
                "practical_hours": _num(g.practical_hours),
                "cf_hours": _num(g.cf_hours),
            }
            for g in u.groups
        ],
    }
