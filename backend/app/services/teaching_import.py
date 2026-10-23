"""
"Paste from Excel" for the department workbook's tabs:

    Courses               Programme | Year | Semester | Sub-class | Students
                          (or one "Course" cell: "BSC.CS Y1S1 (A)")
    Units                 Code | Title | Hours per week | Class length | Room type | Courses
    Groups and lecturers  Unit code | Group | Courses | Students | Lecturer | Staff no. | L | P | CF

"Courses" cells list course labels separated by ";" (or "," or new lines),
and may name another department's courses (servicing). On the groups tab a
unit's rows together replace its groups; "Students" is blank for whole
courses, or one number per course listed ("60; 40"). A lecturer not on the
department's list yet is added to it. Every row is checked on its own and
reported by line; the good rows are kept.
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Identity
from app.errors import ApiError
from app.models import Course, Unit
from app.services.departments import Context, compact, require_enter, require_open
from app.services.lecturers import clean_row, create_lecturer, find_lecturer, split_name
from app.services.teaching import (
    ROOM_TYPES,
    create_course,
    create_unit,
    group_label,
    set_groups,
    term_courses,
    update_course,
    update_unit,
)

ROOM_TYPE_WORDS = {
    "lecture hall": "lecture_hall",
    "lecture_hall": "lecture_hall",
    "hall": "lecture_hall",
    "lecture": "lecture_hall",
    "lab": "lab",
    "laboratory": "lab",
    "computer lab": "lab",
    "science lab": "lab",
    "seminar": "seminar",
    "seminar room": "seminar",
}
_LABEL = re.compile(
    r"^(?P<programme>.+?)\s+Y(?P<year>\d)\s*S(?P<semester>\d)(?:\s*\((?P<sub>[^)]*)\))?\s*$", re.I
)


def _int(value: str | None, what: str, low: int, high: int) -> int:
    if value in (None, ""):
        raise ValueError(f"{what} is required")
    try:
        number = int(float(str(value).replace(",", "")))
    except ValueError as exc:
        raise ValueError(f"{what} '{value}' is not a whole number") from exc
    if not low <= number <= high:
        raise ValueError(f"{what} must be from {low} to {high}")
    return number


def _hours(value: str | None, what: str) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(str(value).replace(",", "."))
    except ValueError as exc:
        raise ValueError(f"{what} '{value}' is not a number") from exc
    if not 0 <= number <= 500:
        raise ValueError(f"{what} must be from 0 to 500")
    return number


MODE_WORDS = {
    "regular": "regular",
    "fulltime": "regular",
    "odel": "odel",
    "odl": "odel",
    "distance": "odel",
    "weekend": "weekend",
    "evening": "evening",
    "schoolbased": "school_based",
    "parttime": "part_time",
}


def _mode(value: str | None) -> str:
    word = "".join(ch for ch in (value or "regular").lower() if ch.isalpha())
    if word not in MODE_WORDS:
        raise ValueError(f"mode '{value}' must be Regular, ODEL, Weekend, Evening, School-based or Part-time")
    return MODE_WORDS[word]


def _list(value: str | None) -> list[str]:
    return [part.strip() for part in re.split(r"[;,\n]+", value or "") if part.strip()]


def _errors(errors: list[dict[str, Any]]) -> dict[str, Any]:
    return {"errors": errors[:200], "error_count": len(errors)}


def _message(exc: Exception) -> str:
    return getattr(exc, "message", None) or str(exc)


# -- courses ---------------------------------------------------------------------------------


def bulk_courses(db: Session, identity: Identity, ctx: Context, rows: list[dict[str, Any]]) -> dict[str, Any]:
    require_enter(ctx)
    require_open(db, ctx)
    created = updated = 0
    errors: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for line, raw in enumerate(rows, start=1):
        r = clean_row(raw)
        try:
            label = r.get("course") or r.get("class")
            match = _LABEL.match(label) if label and not r.get("programme") else None
            if label and not r.get("programme") and match is None:
                raise ValueError(f"'{label}' should look like 'BSC.CS Y1S1' or 'BSC.CS Y1S1 (A)'")
            fields = {
                "programme": " ".join(
                    (match.group("programme") if match else r.get("programme", "")).split()
                ).upper(),
                "year": _int(match.group("year") if match else r.get("year"), "Year", 1, 7),
                "semester": _int(match.group("semester") if match else r.get("semester"), "Semester", 1, 3),
                "sub_class": (
                    (match.group("sub") or "") if match else (r.get("sub_class") or r.get("subclass") or "")
                )
                .strip()
                .upper()[:10],
                "students": _int(r.get("students"), "Students", 1, 5000),
                "mode": _mode(r.get("mode")),
            }
            if not fields["programme"]:
                raise ValueError("Programme is required")
            cohort = f"{fields['programme']}|{fields['year']}|{fields['semester']}|{fields['sub_class']}"
            if cohort in seen:
                raise ValueError(f"this course is also on row {seen[cohort]}")
            seen[cohort] = line
            existing = db.scalar(
                select(Course).where(
                    Course.generator_term_id == ctx.term_id,
                    Course.programme == fields["programme"],
                    Course.year == fields["year"],
                    Course.semester == fields["semester"],
                    Course.sub_class == fields["sub_class"],
                )
            )
            if existing is not None and existing.department_code == ctx.code:
                update_course(
                    db,
                    identity,
                    ctx,
                    str(existing.id),
                    {"students": fields["students"], "mode": fields["mode"]},
                    commit=False,
                )
                updated += 1
            else:
                create_course(db, identity, ctx, fields, commit=False)
                created += 1
        except (ValueError, ApiError) as exc:
            errors.append({"line": line, "message": _message(exc)})
    db.commit()
    return {"created": created, "updated": updated, **_errors(errors)}


# -- units -----------------------------------------------------------------------------------


def _courses_by_label(db: Session, ctx: Context) -> dict[str, Course]:
    return {compact(c.label): c for c in term_courses(db, ctx.term_id)}


def _course_ids(labels: list[str], by_label: dict[str, Course]) -> list[uuid.UUID]:
    ids = []
    for label in labels:
        course = by_label.get(compact(label))
        if course is None:
            raise ValueError(f"no course '{label}' this term; add it on the Courses tab first")
        ids.append(course.id)
    return ids


def bulk_units(db: Session, identity: Identity, ctx: Context, rows: list[dict[str, Any]]) -> dict[str, Any]:
    require_enter(ctx)
    require_open(db, ctx)
    created = updated = 0
    errors: list[dict[str, Any]] = []
    by_label = _courses_by_label(db, ctx)
    seen: dict[str, int] = {}
    for line, raw in enumerate(rows, start=1):
        r = clean_row(raw)
        try:
            code = r.get("code") or r.get("unit_code") or r.get("course_code")
            if not code:
                raise ValueError("Code is required")
            if compact(code) in seen:
                raise ValueError(f"{code} is also on row {seen[compact(code)]}")
            seen[compact(code)] = line
            room_word = (r.get("room_type") or "lecture hall").strip().lower().replace("_", " ")
            if room_word not in ROOM_TYPE_WORDS:
                raise ValueError(f"room type '{r.get('room_type')}' must be {', '.join(ROOM_TYPES.values())}")
            weekly = _int(
                r.get("hours_per_week") or r.get("weekly_hours") or r.get("hours"), "Hours per week", 1, 20
            )
            fields: dict[str, Any] = {
                "code": code,
                "title": r.get("title") or r.get("unit_title") or r.get("course_title"),
                "weekly_hours": weekly,
                "class_length": _int(
                    r.get("class_length") or r.get("session_length") or str(min(weekly, 3)),
                    "Class length",
                    1,
                    6,
                ),
                "room_type": ROOM_TYPE_WORDS[room_word],
            }
            labels = _list(r.get("courses") or r.get("classes"))
            if labels:
                fields["course_ids"] = [str(i) for i in _course_ids(labels, by_label)]
            existing = db.scalar(
                select(Unit).where(Unit.generator_term_id == ctx.term_id, Unit.code_key == compact(code))
            )
            if existing is not None and existing.department_code == ctx.code:
                update_unit(db, identity, ctx, str(existing.id), fields, commit=False)
                updated += 1
            else:
                if not fields["title"]:
                    raise ValueError("Title is required")
                if not labels:
                    raise ValueError("list the courses that take the unit")
                create_unit(db, identity, ctx, fields, commit=False)
                created += 1
        except (ValueError, ApiError) as exc:
            errors.append({"line": line, "message": _message(exc)})
    db.commit()
    return {"created": created, "updated": updated, **_errors(errors)}


# -- groups and lecturers ----------------------------------------------------------------------


def bulk_groups(db: Session, identity: Identity, ctx: Context, rows: list[dict[str, Any]]) -> dict[str, Any]:
    require_enter(ctx)
    require_open(db, ctx)
    errors: list[dict[str, Any]] = []
    by_label = _courses_by_label(db, ctx)
    lecturers_added = 0
    # A unit's rows, gathered first: together they replace its groups.
    by_unit: dict[str, list[tuple[int, dict[str, str]]]] = defaultdict(list)
    for line, raw in enumerate(rows, start=1):
        r = clean_row(raw)
        code = r.get("unit_code") or r.get("code") or r.get("course_code")
        if not code:
            errors.append({"line": line, "message": "Unit code is required"})
            continue
        by_unit[compact(code)].append((line, r))
    units_done = groups_done = 0
    for key, unit_rows in by_unit.items():
        first_line = unit_rows[0][0]
        unit = db.scalar(select(Unit).where(Unit.generator_term_id == ctx.term_id, Unit.code_key == key))
        if unit is None or unit.department_code != ctx.code:
            code = unit_rows[0][1].get("unit_code") or unit_rows[0][1].get("code") or key
            message = (
                f"{code} is {unit.department_code}'s unit"
                if unit is not None
                else f"no unit {code}; add it on the Units tab"
            )
            errors.extend({"line": line, "message": message} for line, _r in unit_rows)
            continue
        try:
            groups: list[dict[str, Any]] = []
            for line, r in unit_rows:
                try:
                    groups.append(_group_row(db, identity, ctx, unit, r, by_label))
                except (ValueError, ApiError) as exc:
                    raise ValueError(f"row {line}: {_message(exc)}") from exc
            added = sum(1 for g in groups if g.pop("_added", False))
            set_groups(db, identity, ctx, str(unit.id), groups, commit=False)
            db.flush()
            lecturers_added += added
            units_done += 1
            groups_done += len(groups)
        except (ValueError, ApiError) as exc:
            db.rollback()
            errors.append({"line": first_line, "message": f"{unit.code}: {_message(exc)}"})
            by_label = _courses_by_label(db, ctx)
            continue
        db.commit()
    extra = f"; {lecturers_added} lecturers added to your list" if lecturers_added else ""
    return {
        "created": groups_done,
        "updated": 0,
        "units": units_done,
        "groups": groups_done,
        "lecturers_added": lecturers_added,
        "message": f"Groups set for {units_done} units ({groups_done} groups){extra}.",
        **_errors(errors),
    }


def _group_row(
    db: Session, identity: Identity, ctx: Context, unit: Unit, r: dict[str, str], by_label: dict[str, Course]
) -> dict[str, Any]:
    labels = _list(r.get("courses") or r.get("classes"))
    ids = (
        _course_ids(labels, by_label)
        if labels
        else [c.course_id for c in unit.courses]  # no courses listed: the whole class
    )
    counts = _list(r.get("students"))
    if counts and len(counts) != len(ids):
        raise ValueError("give one student number per course listed, or leave Students blank")
    members = [
        {"course_id": str(i), "students": _int(counts[n], "Students", 1, 5000) if counts else None}
        for n, i in enumerate(ids)
    ]
    group: dict[str, Any] = {
        "label": group_label(r.get("group")),
        "members": members,
        "lecture_hours": _hours(r.get("l") or r.get("lecture_hours"), "L"),
        "practical_hours": _hours(r.get("p") or r.get("practical_hours"), "P"),
        "cf_hours": _hours(r.get("cf") or r.get("cf_hours"), "CF"),
    }
    staff = r.get("staff_no") or r.get("staff_number")
    name_cell = r.get("lecturer")
    if staff or name_cell:
        title, name, kind = split_name(name_cell or "")
        lecturer = find_lecturer(db, ctx.code, staff, name)
        if lecturer is None:
            if not name:
                raise ValueError(f"no lecturer with staff number {staff} on the Lecturers tab")
            lecturer = create_lecturer(
                db,
                identity,
                ctx,
                {"title": title, "full_name": name, "staff_number": staff, "employment_type": kind.value},
                commit=False,
            )
            group["_added"] = True
        group["lecturer_id"] = str(lecturer.id)
    return group
