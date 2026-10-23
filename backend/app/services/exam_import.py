"""
"Paste from Excel" for exam papers and practicals:

    Exam papers   Codes | Title | Written exam | Examiner | Staff no. | Notes
    Practicals    Unit code | Date | Start | End

"Codes" holds one code, or several for a shared paper ("BITE 131/COSC 130").
"Written exam" No marks the units as having no written exam. A paper is
matched to an existing one by its first code, and updated.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Identity
from app.errors import ApiError
from app.models import ExamPaperUnit, Unit
from app.services.departments import Context, compact, require_enter, require_open
from app.services.exams import KIND, create_paper, save_practical, set_no_written_exam, update_paper
from app.services.lecturers import clean_row, find_lecturer, split_name


def _units_by_code(db: Session, ctx: Context) -> dict[str, Unit]:
    return {u.code_key: u for u in db.scalars(select(Unit).where(Unit.generator_term_id == ctx.term_id))}


def _message(exc: Exception) -> str:
    return getattr(exc, "message", None) or str(exc)


def bulk_papers(db: Session, identity: Identity, ctx: Context, rows: list[dict[str, Any]]) -> dict[str, Any]:
    require_enter(ctx)
    require_open(db, ctx, KIND)
    created = updated = marked = 0
    errors: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for line, raw in enumerate(rows, start=1):
        r = clean_row(raw)
        try:
            cell = r.get("codes") or r.get("unit_codes") or r.get("unit_code") or r.get("code")
            if not cell:
                raise ValueError("Codes is required")
            units = _units_by_code(db, ctx)
            codes = [c.strip() for c in re.split(r"[/;,]+", cell) if c.strip()]
            found = []
            for code in codes:
                key = compact(code)
                if key in seen:
                    raise ValueError(f"{code} is also on row {seen[key]}")
                if key not in units:
                    raise ValueError(f"no unit {code} this term")
                found.append(units[key])
            for code in codes:
                seen[compact(code)] = line
            if (r.get("written_exam") or "yes").strip().lower() in ("no", "n", "false", "0"):
                for u in found:
                    set_no_written_exam(db, identity, ctx, str(u.id), True)
                marked += len(found)
                continue
            fields: dict[str, Any] = {"unit_ids": [str(u.id) for u in found]}
            if r.get("title"):
                fields["title"] = r["title"]
            if r.get("notes"):
                fields["notes"] = r["notes"]
            staff = r.get("staff_no") or r.get("staff_number")
            if staff or r.get("examiner"):
                _title, name, _kind = split_name(r.get("examiner") or "")
                lecturer = find_lecturer(db, ctx.code, staff, name)
                if lecturer is None:
                    raise ValueError(
                        f"no lecturer {r.get('examiner') or staff} on your list; add them on Lecturers"
                    )
                fields["examiner_id"] = str(lecturer.id)
            existing = db.scalar(select(ExamPaperUnit).where(ExamPaperUnit.unit_id == found[0].id))
            if existing is not None:
                update_paper(db, identity, ctx, str(existing.paper_id), fields, commit=False)
                updated += 1
            else:
                create_paper(db, identity, ctx, fields, commit=False)
                created += 1
            db.commit()
        except (ValueError, ApiError) as exc:
            db.rollback()
            errors.append({"line": line, "message": _message(exc)})
    extra = f"; {marked} units marked 'no written exam'" if marked else ""
    return {
        "created": created,
        "updated": updated,
        "message": f"{created} papers added, {updated} updated{extra}.",
        "errors": errors[:200],
        "error_count": len(errors),
    }


def _date(value: str | None) -> date:
    text = (value or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"date '{value}' should look like 2026-11-20 or 20/11/2026")


def _time(value: str | None, what: str) -> time:
    text = (value or "").strip().lower().replace(".", ":")
    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M%p", "%I:%M %p", "%I%p"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"{what} '{value}' should look like 08:30 or 2:30pm")


def bulk_practicals(
    db: Session, identity: Identity, ctx: Context, rows: list[dict[str, Any]]
) -> dict[str, Any]:
    require_enter(ctx)
    require_open(db, ctx, KIND)
    created = 0
    errors: list[dict[str, Any]] = []
    units = _units_by_code(db, ctx)
    for line, raw in enumerate(rows, start=1):
        r = clean_row(raw)
        try:
            code = r.get("unit_code") or r.get("code") or r.get("unit")
            if not code or compact(code) not in units:
                raise ValueError(f"no unit {code or ''} this term".strip())
            save_practical(
                db,
                identity,
                ctx,
                None,
                {
                    "unit_id": str(units[compact(code)].id),
                    "date": _date(r.get("date")),
                    "start_time": _time(r.get("start") or r.get("start_time"), "Start"),
                    "end_time": _time(r.get("end") or r.get("end_time"), "End"),
                },
                commit=False,
            )
            db.commit()
            created += 1
        except (ValueError, ApiError) as exc:
            db.rollback()
            errors.append({"line": line, "message": _message(exc)})
    return {"created": created, "updated": 0, "errors": errors[:200], "error_count": len(errors)}
