"""Lecturers' unavailability for a term: periods of the teaching week they can't be given classes."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth import Identity
from app.clients.smarttt import SmartttClient
from app.errors import ApiError
from app.models import LecturerAvailability
from app.services.allocation import audit, ensure_term
from app.services.timeutil import DAY_ORDER, hhmm, overlaps, parse_hhmm


def _row_dict(row: LecturerAvailability) -> dict[str, Any]:
    return {
        "day_of_week": row.day,
        "start_time": hhmm(row.start_time),
        "end_time": hhmm(row.end_time),
        "reason": row.reason,
    }


def get_availability(
    db: Session, smarttt: SmartttClient, identity: Identity, lecturer_id: str, term_id: str | None
) -> dict[str, Any]:
    data = smarttt.lecturer_sessions(lecturer_id, term_id)
    department_id = int(data["lecturer"]["department"]["id"])
    if not identity.can_view(department_id):
        raise ApiError(403, "FORBIDDEN", "You can only see your own department's lecturers.")
    term = ensure_term(db, data["term"])
    rows = db.scalars(
        select(LecturerAvailability).where(
            LecturerAvailability.term_id == term.id, LecturerAvailability.smarttt_lecturer_id == lecturer_id
        )
    ).all()
    db.commit()
    periods = sorted(
        (_row_dict(r) for r in rows), key=lambda p: (DAY_ORDER[p["day_of_week"]], p["start_time"])
    )
    return {
        "term": data["term"],
        "lecturer": data["lecturer"],
        "unavailable": periods,
        "meetings": data["meetings"],
        "weekly_hours": data["weekly_hours"],
    }


def put_availability(
    db: Session,
    smarttt: SmartttClient,
    identity: Identity,
    lecturer_id: str,
    term_id: str | None,
    periods: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Replaces the lecturer's unavailability for the term. Classes they are
    already allocated at those times are reported (`affected`) so the
    department can re-allocate them; nothing is unallocated automatically.
    """
    data = smarttt.lecturer_sessions(lecturer_id, term_id, fresh=True)
    department_id = int(data["lecturer"]["department"]["id"])
    if not identity.can_allocate(department_id):
        raise ApiError(403, "FORBIDDEN", "Only the lecturer's department can change their availability.")
    term = ensure_term(db, data["term"])

    for i, a in enumerate(periods):
        if parse_hhmm(a["start_time"]) >= parse_hhmm(a["end_time"]):
            raise ApiError(422, "VALIDATION_ERROR", "Each period must start before it ends.")
        for b in periods[i + 1 :]:
            if overlaps(a, b):
                raise ApiError(422, "VALIDATION_ERROR", "Periods overlap; merge them into one.")

    existing = db.scalars(
        select(LecturerAvailability).where(
            LecturerAvailability.term_id == term.id, LecturerAvailability.smarttt_lecturer_id == lecturer_id
        )
    ).all()
    before = [_row_dict(r) for r in existing]
    db.execute(
        delete(LecturerAvailability).where(
            LecturerAvailability.term_id == term.id, LecturerAvailability.smarttt_lecturer_id == lecturer_id
        )
    )
    for p in periods:
        db.add(
            LecturerAvailability(
                term_id=term.id,
                smarttt_lecturer_id=lecturer_id,
                day=p["day_of_week"],
                start_time=parse_hhmm(p["start_time"]),
                end_time=parse_hhmm(p["end_time"]),
                reason=p.get("reason") or "",
                created_by_account_id=identity.account_id,
            )
        )
    audit(
        db,
        identity,
        "availability.replace",
        "lecturer",
        f"{term.smarttt_term_id}:{lecturer_id}",
        {"unavailable": before},
        {"unavailable": periods},
    )
    db.commit()

    affected = sorted({m["code"] for m in data["meetings"] for p in periods if overlaps(m, p)})
    return {**get_availability(db, smarttt, identity, lecturer_id, term_id), "affected": affected}


def department_lecturers(
    db: Session, smarttt: SmartttClient, identity: Identity, department_id: int, term_id: str | None
) -> dict[str, Any]:
    """The department's lecturers with their teaching load this term and their unavailability."""
    if not identity.can_view(department_id):
        raise ApiError(403, "FORBIDDEN", "You can only see your own department's lecturers.")
    term_data = _resolve_term(smarttt, term_id)
    term = ensure_term(db, term_data)
    lecturers = smarttt.lecturers(department_id, term_data["id"])
    periods: dict[str, list[dict[str, Any]]] = {}
    for row in db.scalars(select(LecturerAvailability).where(LecturerAvailability.term_id == term.id)):
        periods.setdefault(row.smarttt_lecturer_id, []).append(_row_dict(row))
    db.commit()
    return {
        "term": term_data,
        "lecturers": [
            {
                **{k: v for k, v in lecturer.items() if k != "meetings"},
                "classes": sorted({m["code"] for m in lecturer.get("meetings", [])}),
                "unavailable": sorted(
                    periods.get(lecturer["id"], []),
                    key=lambda p: (DAY_ORDER[p["day_of_week"]], p["start_time"]),
                ),
            }
            for lecturer in lecturers
        ],
    }


def _resolve_term(smarttt: SmartttClient, term_id: str | None) -> dict[str, Any]:
    terms = smarttt.terms()
    term = next((t for t in terms if (t["id"] == term_id if term_id else t["is_current"])), None)
    if term is None:
        detail = "No such term." if term_id else "No current term is set in SMARTTT."
        raise ApiError(404, "NOT_FOUND", detail)
    return term
