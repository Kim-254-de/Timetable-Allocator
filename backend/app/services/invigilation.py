"""
Invigilators, named by departments on the exam draft the Director shared.

Every paper has one MAIN invigilator, who administers it, collects the
scripts from every room and takes them away; a paper spread over several
rooms also gets one EXTRA invigilator for each extra room (every room but its
main one). Anyone on any department's list can be named; one person (one
staff number) is never in two places in one session, and never over their
duty limit when one is set. The COD publishes the invigilators; the Director
can publish the exam timetable only when every paper and every extra room has
one.

An invigilation's `room` is "" for the main invigilator, else the extra
room's code.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import ROLE_COD, Identity
from app.clients.generator import GeneratorClient
from app.clients.smarttt import SmartttClient
from app.errors import ApiError
from app.models import DepartmentPublication, ExamPaper, Invigilation, Lecturer, utcnow
from app.services.allocation import audit
from app.services.departments import (
    Context,
    context,
    current_publication,
    last_publication,
    require_cod,
    require_enter,
    require_open,
)
from app.services.exams import paper_codes, term_papers
from app.services.lecturers import display_name, get_lecturer, person
from app.services.teaching import publication_dict, term_units

KIND = "invigilators"
MAIN = ""


def _shared(generator: GeneratorClient, ctx: Context) -> dict[str, Any]:
    """The Director's shared exam draft, by paper (our ids)."""
    data = generator.exam_draft(ctx.term_id)
    return {"draft": data.get("draft"), "papers": {p["paper_ref"]: p for p in data.get("papers") or []}}


def _when(p: dict[str, Any]) -> str:
    return f"{p['date']} {p['start_time']}-{p['end_time']}"


def _term_invigilations(db: Session, term_id: str) -> list[Invigilation]:
    return list(
        db.scalars(
            select(Invigilation)
            .join(ExamPaper, ExamPaper.id == Invigilation.paper_id)
            .where(ExamPaper.generator_term_id == term_id)
        )
    )


def problems(
    ctx: Context,
    papers: list[ExamPaper],
    invigilations: list[Invigilation],
    shared: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    named = {(i.paper_id, i.room) for i in invigilations}
    for p in papers:
        where = shared.get(str(p.id))
        if p.department_code != ctx.code or where is None:
            continue
        if (p.id, MAIN) not in named:
            found.append({"code": "no_invigilator", "message": f"Name the main invigilator for {p.title}."})
        for room in _extra_rooms(where):
            if (p.id, room) not in named:
                found.append(
                    {
                        "code": "no_extra_invigilator",
                        "message": f"Name an invigilator for {p.title} in {room}.",
                    }
                )
    return found


def _extra_rooms(where: dict[str, Any]) -> list[str]:
    """Every room of the paper but its main one."""
    if "extra_rooms" in where:
        return list(where["extra_rooms"])
    rooms = list(where.get("rooms") or [])
    return rooms[1:]


def _who(inv: Invigilation | None) -> dict[str, Any] | None:
    if inv is None:
        return None
    return {
        "id": str(inv.lecturer_id),
        "display": display_name(inv.lecturer),
        "department_code": inv.lecturer.department_code,
    }


def board(
    db: Session,
    generator: GeneratorClient,
    smarttt: SmartttClient,
    identity: Identity,
    department_code: str,
    term_id: str | None,
) -> dict[str, Any]:
    ctx = context(generator, smarttt, identity, department_code, term_id)
    shared = _shared(generator, ctx)
    units = {u.id: u for u in term_units(db, ctx.term_id)}
    papers = term_papers(db, ctx.term_id)
    invigilations = _term_invigilations(db, ctx.term_id)
    by_slot = {(i.paper_id, i.room): i for i in invigilations}
    duties: dict[str, int] = defaultdict(int)
    for i in invigilations:
        duties[person(i.lecturer)] += 1
    standing = current_publication(db, ctx.term_id, ctx.code, KIND)
    last = last_publication(db, ctx.term_id, ctx.code, KIND)
    own = [p for p in papers if p.department_code == ctx.code]
    rows = []
    for p in sorted(own, key=lambda p: "/".join(paper_codes(p, units))):
        where = shared["papers"].get(str(p.id))
        extra = _extra_rooms(where) if where else []
        rows.append(
            {
                "paper_id": str(p.id),
                "codes": "/".join(paper_codes(p, units)),
                "title": p.title,
                "date": where["date"] if where else None,
                "session": where["session"] if where else None,
                "start_time": where["start_time"] if where else None,
                "end_time": where["end_time"] if where else None,
                "rooms": where["rooms"] if where else [],
                "main_room": (where.get("main_room") or (where["rooms"][0] if where["rooms"] else None))
                if where
                else None,
                "main": _who(by_slot.get((p.id, MAIN))),
                "extras": [{"room": room, "invigilator": _who(by_slot.get((p.id, room)))} for room in extra],
            }
        )
    lecturers = list(
        db.scalars(select(Lecturer).where(Lecturer.active.is_(True)).order_by(Lecturer.full_name))
    )
    return {
        "term": ctx.term,
        "department": ctx.department,
        "role": ctx.role,
        "draft": shared["draft"],
        "can_edit": ctx.role is not None and standing is None and shared["draft"] is not None,
        "can_publish": ctx.role == ROLE_COD,
        "publication": publication_dict(standing or last),
        "published": standing is not None,
        "papers": rows,
        "lecturers": [
            {
                "id": str(lec.id),
                "display": display_name(lec),
                "department_code": lec.department_code,
                "staff_number": lec.staff_number,
                "duties": duties.get(person(lec), 0),
                "max_exam_duties": lec.max_exam_duties,
                "own": lec.department_code == ctx.code,
            }
            for lec in lecturers
            if lec.staff_number
        ],
        "problems": problems(ctx, papers, invigilations, shared["papers"]),
    }


def set_invigilator(
    db: Session,
    generator: GeneratorClient,
    identity: Identity,
    ctx: Context,
    paper_id: str,
    lecturer_id: str | None,
    room: str = MAIN,
) -> dict[str, Any]:
    """Names or clears a paper's main (room "") or extra-room invigilator, checked for clashes and limits."""
    require_enter(ctx)
    require_open(db, ctx, KIND)
    try:
        paper = db.get(ExamPaper, uuid.UUID(paper_id))
    except ValueError:
        paper = None
    if paper is None or paper.generator_term_id != ctx.term_id or paper.department_code != ctx.code:
        raise ApiError(404, "NOT_FOUND", "No such paper in this department.")
    shared = _shared(generator, ctx)["papers"]
    where = shared.get(str(paper.id))
    if where is None:
        raise ApiError(409, "NOT_IN_DRAFT", "The Director's shared exam draft doesn't have this paper yet.")
    if room != MAIN and room not in _extra_rooms(where):
        raise ApiError(422, "VALIDATION_ERROR", f"{room} isn't one of this paper's extra rooms.")
    existing = db.scalar(
        select(Invigilation).where(Invigilation.paper_id == paper.id, Invigilation.room == room)
    )
    if lecturer_id is None:
        if existing is not None:
            audit(db, identity, "invigilation.clear", "exam_paper", str(paper.id), None, None)
            db.delete(existing)
            db.commit()
        return {"paper_id": str(paper.id), "room": room, "invigilator_id": None}
    lecturer = get_lecturer(db, lecturer_id)
    if not lecturer.active or not lecturer.staff_number:
        raise ApiError(
            422, "VALIDATION_ERROR", f"{lecturer.full_name} needs to be active, with a staff number."
        )
    who = person(lecturer)
    duties = 0
    for other in _term_invigilations(db, ctx.term_id):
        if (other.paper_id == paper.id and other.room == room) or person(other.lecturer) != who:
            continue
        duties += 1
        there = shared.get(str(other.paper_id))
        # Another paper, or another room of this one, in the same session: they can't be in both.
        if there is not None and there["date"] == where["date"] and there["session"] == where["session"]:
            other_paper = db.get(ExamPaper, other.paper_id)
            raise ApiError(
                409,
                "INVIGILATOR_BUSY",
                f"{lecturer.full_name} already invigilates {other_paper.title if other_paper else 'a paper'} "
                f"on {_when(where)}.",
            )
    limit = min(
        (lec.max_exam_duties for lec in _same_person(db, lecturer) if lec.max_exam_duties), default=None
    )
    if limit is not None and duties + 1 > limit:
        raise ApiError(
            409, "DUTY_LIMIT", f"{lecturer.full_name} already has {duties} duties; the limit is {limit}."
        )
    if existing is None:
        existing = Invigilation(
            paper_id=paper.id, room=room, lecturer_id=lecturer.id, entered_by_name=identity.actor
        )
        db.add(existing)
    else:
        existing.lecturer_id = lecturer.id
        existing.lecturer = lecturer
        existing.entered_by_name = identity.actor
    db.flush()
    audit(
        db,
        identity,
        "invigilation.set",
        "exam_paper",
        str(paper.id),
        None,
        {"lecturer": lecturer.staff_number, "room": room or "main"},
    )
    db.commit()
    return {"paper_id": str(paper.id), "room": room, "invigilator_id": str(lecturer.id)}


def _same_person(db: Session, lecturer: Lecturer) -> list[Lecturer]:
    """The person on every department's list (same staff number)."""
    if not lecturer.staff_number:
        return [lecturer]
    return list(db.scalars(select(Lecturer).where(Lecturer.staff_number == lecturer.staff_number)))


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
    current = board(db, generator, smarttt, identity, department_code, ctx.term_id)
    if current["draft"] is None:
        raise ApiError(409, "NO_DRAFT", "The Director hasn't shared an exam draft yet.")
    if current["problems"]:
        raise ApiError(
            409,
            "NOT_READY",
            f"{len(current['problems'])} papers have no invigilator yet.",
            {"problems": current["problems"]},
        )
    db.add(
        DepartmentPublication(
            generator_term_id=ctx.term_id,
            department_code=ctx.code,
            department_name=ctx.department["name"],
            kind=KIND,
            published_by_account_id=identity.account_id,
            published_by_name=identity.actor,
            unit_count=len(current["papers"]),
            group_count=0,
        )
    )
    audit(
        db, identity, "department.publish_invigilators", "department", ctx.code, None, {"term": ctx.term_id}
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
        raise ApiError(409, "NOT_PUBLISHED", "This department's invigilators haven't been published.")
    standing.reopened_at = utcnow()
    standing.reopened_by_name = identity.actor
    audit(db, identity, "department.reopen_invigilators", "department", ctx.code, None, {"term": ctx.term_id})
    db.commit()
    return board(db, generator, smarttt, identity, department_code, ctx.term_id)


def for_generator(db: Session, term_id: str) -> dict[str, Any]:
    """Each paper's invigilator, from departments that published: {paper id: {room: {staff_number, name}}}."""
    published = {
        p.department_code
        for p in db.scalars(
            select(DepartmentPublication).where(
                DepartmentPublication.generator_term_id == term_id,
                DepartmentPublication.kind == KIND,
                DepartmentPublication.reopened_at.is_(None),
            )
        )
    }
    out: dict[str, dict[str, dict[str, str | None]]] = defaultdict(dict)
    for inv in _term_invigilations(db, term_id):
        paper = db.get(ExamPaper, inv.paper_id)
        if paper is None or paper.department_code not in published:
            continue
        out[str(inv.paper_id)][inv.room] = {
            "staff_number": inv.lecturer.staff_number,
            "name": display_name(inv.lecturer),
        }
    return dict(out)
