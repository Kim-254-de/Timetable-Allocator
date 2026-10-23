"""
Terms, departments and who may do what.

Terms are the Timetable Generator's: the Director opens a term there, and
departments enter their teaching for it here. Departments are identified by
their code ("CS"); a signed-in member of staff belongs to a department when
SMARTTT lists them under it, as its COD (who publishes) or allocation staff
(who enter). The Directorate sees every department, read-only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import ROLE_COD, Identity
from app.clients.generator import GeneratorClient
from app.clients.smarttt import SmartttClient
from app.errors import ApiError
from app.models import DepartmentPublication


def compact(value: str) -> str:
    """'COSC 103' -> 'COSC103': codes compared without spaces or punctuation, in upper case."""
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


@dataclass
class Context:
    term: dict[str, Any]
    department: dict[str, Any]  # {code, name}
    role: str | None  # cod | admin | editor | None (viewing only)

    @property
    def code(self) -> str:
        return compact(self.department["code"])

    @property
    def term_id(self) -> str:
        return str(self.term["id"])


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


def all_departments(smarttt: SmartttClient) -> list[dict[str, Any]]:
    """Every department, as SMARTTT lists them: {code, name}."""
    return [{"code": str(d["code"]), "name": str(d["name"])} for d in smarttt.departments()]


def visible_departments(identity: Identity, smarttt: SmartttClient) -> list[dict[str, Any]]:
    """The departments this person may open: every one for the Directorate, else their own."""
    out: dict[str, dict[str, Any]] = {}
    for d in identity.departments:
        out[compact(d.code)] = {"code": d.code, "name": d.name, "role": d.role}
    if identity.timetabling_office:
        for other in all_departments(smarttt):
            out.setdefault(compact(other["code"]), {**other, "role": None})
    return sorted(out.values(), key=lambda d: d["name"])


def context(
    generator: GeneratorClient,
    smarttt: SmartttClient,
    identity: Identity,
    department_code: str,
    term_id: str | None,
) -> Context:
    term = pick_term(generator, term_id)
    mine = next((d for d in identity.departments if compact(d.code) == compact(department_code)), None)
    if mine is not None:
        return Context(term=term, department={"code": mine.code, "name": mine.name}, role=mine.role)
    if not identity.timetabling_office:
        raise ApiError(403, "FORBIDDEN", "You can only open your own department.")
    found = next(
        (d for d in all_departments(smarttt) if compact(d["code"]) == compact(department_code)), None
    )
    if found is None:
        raise ApiError(404, "NOT_FOUND", "No such department.")
    return Context(term=term, department=found, role=None)


def require_enter(ctx: Context) -> None:
    if ctx.role is None:
        raise ApiError(403, "FORBIDDEN", "Only this department's COD and allocation staff can change it.")


def require_cod(ctx: Context) -> None:
    if ctx.role != ROLE_COD:
        raise ApiError(403, "FORBIDDEN", "Only the Chair of Department can publish or reopen.")


def current_publication(db: Session, term_id: str, department_code: str) -> DepartmentPublication | None:
    """The department's publication that stands (not reopened), if any."""
    return db.scalar(
        select(DepartmentPublication)
        .where(
            DepartmentPublication.generator_term_id == term_id,
            DepartmentPublication.department_code == department_code,
            DepartmentPublication.reopened_at.is_(None),
        )
        .order_by(DepartmentPublication.published_at.desc())
        .limit(1)
    )


def last_publication(db: Session, term_id: str, department_code: str) -> DepartmentPublication | None:
    """The department's latest publication, standing or reopened."""
    return db.scalar(
        select(DepartmentPublication)
        .where(
            DepartmentPublication.generator_term_id == term_id,
            DepartmentPublication.department_code == department_code,
        )
        .order_by(DepartmentPublication.published_at.desc())
        .limit(1)
    )


def require_open(db: Session, ctx: Context) -> None:
    if current_publication(db, ctx.term_id, ctx.code) is not None:
        raise ApiError(
            409,
            "PUBLISHED",
            "This department's list has been published. The COD must reopen it before it can change.",
        )
