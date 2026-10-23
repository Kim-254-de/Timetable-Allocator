"""
Each department's own list of lecturers.

A lecturer teaching for two departments can be on both lists with the same
staff number; the staff number is how the workload check, the Generator's
solver and SMARTTT know them as one person, so every lecturer given a group
needs one.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import Identity
from app.errors import ApiError
from app.models import EmploymentType, Lecturer, UnitGroup
from app.services.allocation import audit
from app.services.departments import Context, require_enter

EMPLOYMENT_SHORT = {EmploymentType.FULL_TIME: "FT", EmploymentType.PART_TIME: "PT"}


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
        "max_exam_duties": lecturer.max_exam_duties,
        "active": lecturer.active,
    }


def display_name(lecturer: Lecturer) -> str:
    title = f"{lecturer.title} " if lecturer.title else ""
    return f"{title}{lecturer.full_name} ({EMPLOYMENT_SHORT[lecturer.employment_type]})"


def person(lecturer: Lecturer) -> str:
    """One person across departments' lists: the staff number when known."""
    return f"staff:{lecturer.staff_number.upper()}" if lecturer.staff_number else f"id:{lecturer.id}"


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
    for key in (
        "title",
        "full_name",
        "staff_number",
        "phone",
        "email",
        "max_weekly_hours",
        "max_exam_duties",
        "active",
    ):
        if key in fields:
            setattr(lecturer, key, fields[key] if fields[key] != "" or key != "staff_number" else None)
    if fields.get("employment_type") is not None:
        lecturer.employment_type = EmploymentType(fields["employment_type"])


def create_lecturer(
    db: Session, identity: Identity, ctx: Context, fields: dict[str, Any], commit: bool = True
) -> Lecturer:
    require_enter(ctx)
    lecturer = Lecturer(department_code=ctx.code, full_name="", title="", phone="", email="")
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
    require_enter(ctx)
    before = lecturer_dict(lecturer)
    _apply_lecturer(db, lecturer, fields)
    db.flush()
    audit(db, identity, "lecturer.update", "lecturer", str(lecturer.id), before, lecturer_dict(lecturer))
    db.commit()
    return lecturer


def delete_lecturer(db: Session, identity: Identity, ctx: Context, lecturer: Lecturer) -> None:
    require_enter(ctx)
    used = db.scalar(select(func.count()).select_from(UnitGroup).where(UnitGroup.lecturer_id == lecturer.id))
    if used:
        raise ApiError(
            409,
            "IN_USE",
            f"{lecturer.full_name} teaches {used} groups. Change those first, or mark them inactive.",
        )
    audit(db, identity, "lecturer.delete", "lecturer", str(lecturer.id), lecturer_dict(lecturer), None)
    db.delete(lecturer)
    db.commit()


def lecturer_ctx_check(lecturer: Lecturer, ctx: Context) -> None:
    if lecturer.department_code != ctx.code:
        raise ApiError(403, "FORBIDDEN", "That lecturer is on another department's list.")


# -- pasting from Excel or Word -------------------------------------------------------------

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


def clean_row(row: dict[str, Any]) -> dict[str, str]:
    """A pasted row keyed by its column heading in snake case ('Staff no.' -> 'staff_no'), blanks dropped."""
    out: dict[str, str] = {}
    for key, value in row.items():
        k = re.sub(r"[^a-z0-9]+", "_", str(key).strip().lower()).strip("_")
        v = str(value).strip() if value is not None else ""
        if v:
            out[k] = v
    return out


def same_name(a: str, b: str) -> bool:
    """'James Ng'ang'a' and 'james  nganga' are one name: letters only, any case."""
    return re.sub(r"[^a-z]", "", a.lower()) == re.sub(r"[^a-z]", "", b.lower())


def find_lecturer(db: Session, department_code: str, staff_number: str | None, name: str) -> Lecturer | None:
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


def bulk_lecturers(
    db: Session, identity: Identity, ctx: Context, rows: list[dict[str, Any]]
) -> dict[str, Any]:
    """The Lecturers tab of the workbook: Name, Title, FT/PT, Staff no., Phone, Email, Max hours."""
    require_enter(ctx)
    created = updated = 0
    errors: list[dict[str, Any]] = []
    # Each lecturer once per file: a repeat is a mistake (two people given one
    # staff number), never a reason to overwrite the earlier row.
    staff_rows: dict[str, tuple[int, str]] = {}
    lecturer_rows: dict[uuid.UUID, int] = {}
    for line, raw in enumerate(rows, start=1):
        r = clean_row(raw)
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
            existing = find_lecturer(db, ctx.code, staff or None, name)
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
