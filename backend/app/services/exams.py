"""
What departments enter for the exam timetable, and publish to the Director.

Each department lists its written exam papers, built from its units: all
groups of a unit sit one paper, and one paper can carry several units' codes
("BITE 131/COSC 130"). A unit is on at most one paper per term, so a code
listed twice is refused. A unit with no written exam is marked so. Practicals
are on dates the department sets; the Generator only shows them.

The COD publishes the paper list (and practicals), which locks it until they
reopen it. The Generator imports it, places every paper in a session and its
students in rooms; departments then name invigilators (services.invigilation).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict
from datetime import date, time
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth import ROLE_COD, Identity
from app.clients.generator import GeneratorClient
from app.clients.smarttt import SmartttClient
from app.errors import ApiError
from app.models import (
    Course,
    DepartmentPublication,
    ExamPaper,
    ExamPaperUnit,
    NoWrittenExam,
    Practical,
    Unit,
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
    require_cod,
    require_enter,
    require_open,
)
from app.services.lecturers import department_lecturers, display_name
from app.services.teaching import _lecturer_for, course_dict, publication_dict, term_courses, term_units

KIND = "exams"


def _uuid(value: str, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except ValueError as exc:
        raise ApiError(404, "NOT_FOUND", f"No such {what}.") from exc


def term_papers(db: Session, term_id: str) -> list[ExamPaper]:
    return list(db.scalars(select(ExamPaper).where(ExamPaper.generator_term_id == term_id)))


def paper_codes(paper: ExamPaper, units: dict[uuid.UUID, Unit]) -> list[str]:
    return sorted(units[u.unit_id].code for u in paper.units if u.unit_id in units)


def paper_courses(
    paper: ExamPaper, units: dict[uuid.UUID, Unit], courses: dict[uuid.UUID, Course]
) -> list[Course]:
    """The cohorts that sit the paper: every course taking any of its units, once."""
    ids = {c.course_id for u in paper.units if u.unit_id in units for c in units[u.unit_id].courses}
    return sorted((courses[i] for i in ids if i in courses), key=lambda c: c.label)


def default_examiner(unit: Unit) -> Any:
    """The lecturer of the whole class, or of the first group of a split unit."""
    for g in unit.groups:
        if g.lecturer is not None:
            return g.lecturer
    return None


def signature(paper: ExamPaper, units: dict[uuid.UUID, Unit]) -> str:
    data = {
        "codes": paper_codes(paper, units),
        "title": paper.title,
        "examiner": paper.examiner.staff_number if paper.examiner else None,
        "notes": paper.notes,
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def paper_dict(
    p: ExamPaper,
    units: dict[uuid.UUID, Unit],
    courses: dict[uuid.UUID, Course],
    ever_published: bool,
) -> dict[str, Any]:
    sitting = paper_courses(p, units, courses)
    return {
        "id": str(p.id),
        "department_code": p.department_code,
        "codes": "/".join(paper_codes(p, units)),
        "units": sorted(
            (
                {
                    "id": str(units[u.unit_id].id),
                    "code": units[u.unit_id].code,
                    "department_code": units[u.unit_id].department_code,
                }
                for u in p.units
                if u.unit_id in units
            ),
            key=lambda u: u["code"],
        ),
        "title": p.title,
        "examiner_id": str(p.examiner_id) if p.examiner_id else None,
        "examiner": display_name(p.examiner) if p.examiner else None,
        "notes": p.notes,
        "class_rows": [c.label for c in sitting],
        "students": sum(c.students for c in sitting),
        "changed_since_published": ever_published and p.published_signature != signature(p, units),
    }


def practical_dict(p: Practical, units: dict[uuid.UUID, Unit]) -> dict[str, Any]:
    unit = units.get(p.unit_id)
    return {
        "id": str(p.id),
        "unit_id": str(p.unit_id),
        "unit_code": unit.code if unit else "?",
        "unit_title": unit.title if unit else "",
        "date": p.date.isoformat(),
        "start_time": p.start_time.strftime("%H:%M"),
        "end_time": p.end_time.strftime("%H:%M"),
    }


def problems(
    ctx_code: str, own_units: list[Unit], papers: list[ExamPaper], no_exam: set[uuid.UUID]
) -> list[dict[str, Any]]:
    """What must be fixed before the COD can publish the paper list."""
    found: list[dict[str, Any]] = []
    on_paper = {u.unit_id for p in papers for u in p.units}
    own_papers = [p for p in papers if p.department_code == ctx_code]
    if not own_units:
        found.append({"code": "no_units", "message": "Enter your units (Units & groups) first."})
    for u in own_units:
        if u.id not in on_paper and u.id not in no_exam:
            found.append(
                {
                    "code": "unit_not_examined",
                    "message": f"{u.code} is on no paper; add it to one, or mark it 'no written exam'.",
                }
            )
    for p in own_papers:
        if p.examiner_id is None:
            found.append({"code": "no_examiner", "message": f"Give {p.title} an examiner."})
    return found


def board(
    db: Session,
    generator: GeneratorClient,
    smarttt: SmartttClient,
    identity: Identity,
    department_code: str,
    term_id: str | None,
) -> dict[str, Any]:
    """A department's exam papers, practicals and what blocks publishing them."""
    ctx = context(generator, smarttt, identity, department_code, term_id)
    units = {u.id: u for u in term_units(db, ctx.term_id)}
    courses = {c.id: c for c in term_courses(db, ctx.term_id)}
    own_units = sorted((u for u in units.values() if u.department_code == ctx.code), key=lambda u: u.code_key)
    papers = term_papers(db, ctx.term_id)
    no_exam = set(db.scalars(select(NoWrittenExam.unit_id)))
    standing = current_publication(db, ctx.term_id, ctx.code, KIND)
    last = last_publication(db, ctx.term_id, ctx.code, KIND)
    paper_of = {u.unit_id: p for p in papers for u in p.units}
    found = problems(ctx.code, own_units, papers, no_exam)
    own_papers = sorted(
        (paper_dict(p, units, courses, last is not None) for p in papers if p.department_code == ctx.code),
        key=lambda p: p["codes"],
    )
    practicals = db.scalars(
        select(Practical).where(
            Practical.generator_term_id == ctx.term_id, Practical.department_code == ctx.code
        )
    )
    return {
        "term": ctx.term,
        "department": ctx.department,
        "role": ctx.role,
        "can_edit": ctx.role is not None and standing is None,
        "can_publish": ctx.role == ROLE_COD,
        "publication": publication_dict(standing or last),
        "published": standing is not None,
        "papers": own_papers,
        "units": [
            {
                "id": str(u.id),
                "code": u.code,
                "title": u.title,
                "no_written_exam": u.id in no_exam,
                "paper_id": str(paper_of[u.id].id) if u.id in paper_of else None,
                "paper_codes": "/".join(paper_codes(paper_of[u.id], units)) if u.id in paper_of else None,
                "paper_department": paper_of[u.id].department_code if u.id in paper_of else None,
                "default_examiner_id": str(e.id) if (e := default_examiner(u)) else None,
            }
            for u in own_units
        ],
        # Other departments' units, for a paper shared with them ("BITE 131/COSC 130").
        "other_units": [
            {"id": str(u.id), "code": u.code, "title": u.title, "department_code": u.department_code}
            for u in sorted(units.values(), key=lambda u: u.code_key)
            if u.department_code != ctx.code and u.id not in paper_of
        ],
        "practicals": sorted(
            (practical_dict(p, units) for p in practicals), key=lambda p: (p["date"], p["start_time"])
        ),
        "lecturers": [
            {
                "id": str(lec.id),
                "display": display_name(lec),
                "staff_number": lec.staff_number,
                "active": lec.active,
            }
            for lec in department_lecturers(db, ctx.code)
        ],
        "problems": found,
        "summary": {
            "papers": len(own_papers),
            "students": sum(p["students"] for p in own_papers),
            "changed": sum(1 for p in own_papers if p["changed_since_published"]),
            "problems": len(found),
        },
    }


# -- papers ----------------------------------------------------------------------------------


def _check_units(db: Session, ctx: Context, unit_ids: list[str], paper: ExamPaper | None) -> list[uuid.UUID]:
    """The paper's units: in this term, at least one this department's, none on another paper."""
    ids = [_uuid(i, "unit") for i in dict.fromkeys(unit_ids)]
    if not ids:
        raise ApiError(422, "VALIDATION_ERROR", "Choose the unit (or units) the paper covers.")
    units = {
        u.id: u
        for u in db.scalars(select(Unit).where(Unit.generator_term_id == ctx.term_id, Unit.id.in_(ids)))
    }
    if len(units) != len(ids):
        raise ApiError(422, "VALIDATION_ERROR", "A unit chosen isn't in this term.")
    if not any(u.department_code == ctx.code for u in units.values()):
        raise ApiError(422, "VALIDATION_ERROR", "A paper needs at least one of your department's units.")
    for link in db.scalars(select(ExamPaperUnit).where(ExamPaperUnit.unit_id.in_(ids))):
        if paper is None or link.paper_id != paper.id:
            raise ApiError(409, "UNIT_ON_PAPER", f"{units[link.unit_id].code} is already on another paper.")
    marked = set(db.scalars(select(NoWrittenExam.unit_id).where(NoWrittenExam.unit_id.in_(ids))))
    if marked:
        raise ApiError(
            409, "NO_WRITTEN_EXAM", f"{', '.join(units[i].code for i in marked)} is marked 'no written exam'."
        )
    return ids


def _get_paper(db: Session, ctx: Context, paper_id: str) -> ExamPaper:
    paper = db.get(ExamPaper, _uuid(paper_id, "paper"))
    if paper is None or paper.generator_term_id != ctx.term_id or paper.department_code != ctx.code:
        raise ApiError(404, "NOT_FOUND", "No such paper in this department.")
    return paper


def _paper_audit(p: ExamPaper) -> dict[str, Any]:
    return {
        "units": sorted(str(u.unit_id) for u in p.units),
        "title": p.title,
        "examiner_id": str(p.examiner_id) if p.examiner_id else None,
        "notes": p.notes,
    }


def create_paper(
    db: Session, identity: Identity, ctx: Context, fields: dict[str, Any], commit: bool = True
) -> ExamPaper:
    require_enter(ctx)
    require_open(db, ctx, KIND)
    ids = _check_units(db, ctx, list(fields.get("unit_ids") or []), None)
    units = [db.get(Unit, i) for i in ids]
    first = next(u for u in units if u is not None and u.department_code == ctx.code)
    examiner = (
        _lecturer_for(db, ctx, fields["examiner_id"])
        if fields.get("examiner_id")
        else default_examiner(first)
    )
    paper = ExamPaper(
        generator_term_id=ctx.term_id,
        department_code=ctx.code,
        title=(fields.get("title") or "").strip() or first.title,
        examiner=examiner,
        notes=(fields.get("notes") or "").strip(),
        units=[ExamPaperUnit(unit_id=i) for i in ids],
    )
    db.add(paper)
    db.flush()
    audit(db, identity, "exam_paper.create", "exam_paper", str(paper.id), None, _paper_audit(paper))
    if commit:
        db.commit()
    return paper


def update_paper(
    db: Session, identity: Identity, ctx: Context, paper_id: str, fields: dict[str, Any], commit: bool = True
) -> ExamPaper:
    require_enter(ctx)
    require_open(db, ctx, KIND)
    paper = _get_paper(db, ctx, paper_id)
    before = _paper_audit(paper)
    ids = _check_units(db, ctx, list(fields["unit_ids"]), paper) if fields.get("unit_ids") else None
    examiner = _lecturer_for(db, ctx, fields["examiner_id"]) if fields.get("examiner_id") else None
    if ids is not None:
        paper.units = [u for u in paper.units if u.unit_id in ids] + [
            ExamPaperUnit(unit_id=i) for i in ids if i not in {u.unit_id for u in paper.units}
        ]
    if fields.get("title"):
        paper.title = fields["title"].strip()
    if "examiner_id" in fields:
        paper.examiner = examiner
    if fields.get("notes") is not None:
        paper.notes = fields["notes"].strip()
    db.flush()
    audit(db, identity, "exam_paper.update", "exam_paper", str(paper.id), before, _paper_audit(paper))
    if commit:
        db.commit()
    return paper


def delete_paper(db: Session, identity: Identity, ctx: Context, paper_id: str) -> None:
    require_enter(ctx)
    require_open(db, ctx, KIND)
    paper = _get_paper(db, ctx, paper_id)
    audit(db, identity, "exam_paper.delete", "exam_paper", str(paper.id), _paper_audit(paper), None)
    db.delete(paper)
    db.commit()


def start_from_units(db: Session, identity: Identity, ctx: Context) -> dict[str, Any]:
    """A paper per unit not on one yet (nor marked no written exam), titled as the unit."""
    require_enter(ctx)
    require_open(db, ctx, KIND)
    on_paper = set(db.scalars(select(ExamPaperUnit.unit_id)))
    no_exam = set(db.scalars(select(NoWrittenExam.unit_id)))
    created = 0
    for u in term_units(db, ctx.term_id):
        if u.department_code == ctx.code and u.id not in on_paper and u.id not in no_exam:
            create_paper(db, identity, ctx, {"unit_ids": [str(u.id)]}, commit=False)
            created += 1
    db.commit()
    return {"created": created}


def set_no_written_exam(db: Session, identity: Identity, ctx: Context, unit_id: str, value: bool) -> None:
    require_enter(ctx)
    require_open(db, ctx, KIND)
    unit = db.get(Unit, _uuid(unit_id, "unit"))
    if unit is None or unit.generator_term_id != ctx.term_id or unit.department_code != ctx.code:
        raise ApiError(404, "NOT_FOUND", "No such unit in this department.")
    if value:
        if db.scalar(select(ExamPaperUnit).where(ExamPaperUnit.unit_id == unit.id)) is not None:
            raise ApiError(409, "UNIT_ON_PAPER", f"{unit.code} is on a paper; take it off the paper first.")
        if db.get(NoWrittenExam, unit.id) is None:
            db.add(NoWrittenExam(unit_id=unit.id))
    else:
        db.execute(delete(NoWrittenExam).where(NoWrittenExam.unit_id == unit.id))
    audit(db, identity, "unit.no_written_exam", "unit", str(unit.id), None, {"no_written_exam": value})
    db.commit()


# -- practicals ------------------------------------------------------------------------------


def _practical_values(db: Session, ctx: Context, fields: dict[str, Any]) -> dict[str, Any]:
    unit = db.get(Unit, _uuid(fields["unit_id"], "unit"))
    if unit is None or unit.generator_term_id != ctx.term_id or unit.department_code != ctx.code:
        raise ApiError(422, "VALIDATION_ERROR", "Choose one of your department's units.")
    start, end = fields["start_time"], fields["end_time"]
    if not isinstance(start, time) or not isinstance(end, time) or start >= end:
        raise ApiError(422, "VALIDATION_ERROR", "A practical must end after it starts.")
    if not isinstance(fields["date"], date) or fields["date"].weekday() > 4:
        raise ApiError(422, "VALIDATION_ERROR", "Practicals are on weekdays.")
    return {"unit_id": unit.id, "date": fields["date"], "start_time": start, "end_time": end}


def save_practical(
    db: Session,
    identity: Identity,
    ctx: Context,
    practical_id: str | None,
    fields: dict[str, Any],
    commit: bool = True,
) -> Practical:
    require_enter(ctx)
    require_open(db, ctx, KIND)
    values = _practical_values(db, ctx, fields)
    if practical_id is None:
        practical = Practical(generator_term_id=ctx.term_id, department_code=ctx.code, **values)
        db.add(practical)
    else:
        found = db.get(Practical, _uuid(practical_id, "practical"))
        if found is None or found.generator_term_id != ctx.term_id or found.department_code != ctx.code:
            raise ApiError(404, "NOT_FOUND", "No such practical in this department.")
        practical = found
        for key, value in values.items():
            setattr(practical, key, value)
    db.flush()
    audit(
        db,
        identity,
        "practical.save",
        "practical",
        str(practical.id),
        None,
        {k: str(v) for k, v in values.items()},
    )
    if commit:
        db.commit()
    return practical


def delete_practical(db: Session, identity: Identity, ctx: Context, practical_id: str) -> None:
    require_enter(ctx)
    require_open(db, ctx, KIND)
    found = db.get(Practical, _uuid(practical_id, "practical"))
    if found is None or found.generator_term_id != ctx.term_id or found.department_code != ctx.code:
        raise ApiError(404, "NOT_FOUND", "No such practical in this department.")
    audit(db, identity, "practical.delete", "practical", str(found.id), None, None)
    db.delete(found)
    db.commit()


# -- publishing ------------------------------------------------------------------------------


def publish(
    db: Session,
    generator: GeneratorClient,
    smarttt: SmartttClient,
    identity: Identity,
    department_code: str,
    term_id: str | None,
) -> dict[str, Any]:
    ctx = context(generator, smarttt, identity, department_code, term_id)
    require_cod(ctx)
    require_open(db, ctx, KIND)
    units = {u.id: u for u in term_units(db, ctx.term_id)}
    own_units = [u for u in units.values() if u.department_code == ctx.code]
    papers = term_papers(db, ctx.term_id)
    no_exam = set(db.scalars(select(NoWrittenExam.unit_id)))
    found = problems(ctx.code, own_units, papers, no_exam)
    if found:
        raise ApiError(
            409,
            "NOT_READY",
            f"{len(found)} things must be fixed before publishing: {found[0]['message']}",
            {"problems": found[:50]},
        )
    own = [p for p in papers if p.department_code == ctx.code]
    for p in own:
        p.published_signature = signature(p, units)
    db.add(
        DepartmentPublication(
            generator_term_id=ctx.term_id,
            department_code=ctx.code,
            department_name=ctx.department["name"],
            kind=KIND,
            published_by_account_id=identity.account_id,
            published_by_name=identity.actor,
            unit_count=len(own),
            group_count=0,
        )
    )
    audit(
        db,
        identity,
        "department.publish_exams",
        "department",
        ctx.code,
        None,
        {"term": ctx.term_id, "papers": len(own)},
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
    standing = current_publication(db, ctx.term_id, ctx.code, KIND)
    if standing is None:
        raise ApiError(409, "NOT_PUBLISHED", "This department's exam papers haven't been published.")
    standing.reopened_at = utcnow()
    standing.reopened_by_name = identity.actor
    audit(db, identity, "department.reopen_exams", "department", ctx.code, None, {"term": ctx.term_id})
    db.commit()
    return board(db, generator, smarttt, identity, department_code, ctx.term_id)


# -- what the Generator reads -----------------------------------------------------------------


def submissions(db: Session, smarttt: SmartttClient, term_id: str) -> dict[str, Any]:
    """
    Every department's published exam papers, with the class rows (courses)
    that sit each and their students, its practicals, and the departments
    that haven't published.
    """
    units = {u.id: u for u in term_units(db, term_id)}
    courses = {c.id: c for c in term_courses(db, term_id)}
    papers = term_papers(db, term_id)
    latest: dict[str, DepartmentPublication] = {}
    for row in db.scalars(
        select(DepartmentPublication)
        .where(DepartmentPublication.generator_term_id == term_id, DepartmentPublication.kind == KIND)
        .order_by(DepartmentPublication.published_at)
    ):
        latest[row.department_code] = row
    try:
        known = {compact(d["code"]): d["name"] for d in all_departments(smarttt)}
    except ApiError:
        known = {}
    for code in {*(p.department_code for p in papers), *latest}:
        known.setdefault(code, latest[code].department_name if code in latest else code)
    by_department: dict[str, list[ExamPaper]] = defaultdict(list)
    for p in papers:
        by_department[p.department_code].append(p)
    practicals_by: dict[str, list[Practical]] = defaultdict(list)
    for pr in db.scalars(select(Practical).where(Practical.generator_term_id == term_id)):
        practicals_by[pr.department_code].append(pr)

    published: list[dict[str, Any]] = []
    waiting: list[dict[str, Any]] = []
    needed: set[uuid.UUID] = set()
    for code, name in sorted(known.items(), key=lambda kv: kv[1]):
        pub = latest.get(code)
        if pub is None or pub.reopened_at is not None:
            waiting.append(
                {
                    "code": code,
                    "name": name,
                    "reopened_at": pub.reopened_at.isoformat() if pub and pub.reopened_at else None,
                }
            )
            continue
        out = []
        for p in sorted(by_department.get(code, []), key=lambda p: "/".join(paper_codes(p, units))):
            sitting = paper_courses(p, units, courses)
            needed.update(c.id for c in sitting)
            out.append(
                {
                    "id": str(p.id),
                    "codes": paper_codes(p, units),
                    "title": p.title,
                    "examiner": (
                        {"staff_number": p.examiner.staff_number, "name": display_name(p.examiner)}
                        if p.examiner
                        else None
                    ),
                    "notes": p.notes,
                    "rows": [
                        {"course_id": str(c.id), "students": c.students, "mode": c.mode} for c in sitting
                    ],
                    "students": sum(c.students for c in sitting),
                }
            )
        published.append(
            {
                "code": code,
                "name": name,
                "published_at": pub.published_at.isoformat(),
                "published_by": pub.published_by_name,
                "papers": out,
                "practicals": [
                    {
                        "id": str(pr.id),
                        "codes": [units[pr.unit_id].code] if pr.unit_id in units else [],
                        "title": units[pr.unit_id].title if pr.unit_id in units else "",
                        "date": pr.date.isoformat(),
                        "start_time": pr.start_time.strftime("%H:%M"),
                        "end_time": pr.end_time.strftime("%H:%M"),
                    }
                    for pr in practicals_by.get(code, [])
                ],
            }
        )
    return {
        "term_id": term_id,
        "courses": [course_dict(courses[i]) for i in sorted(needed, key=lambda i: courses[i].label)],
        "published": published,
        "not_published": waiting,
    }
