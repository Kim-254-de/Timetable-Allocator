"""HTTP API, mounted under /api. Every response uses the {success, data} wrapper (app.errors)."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.schemas import SECTION_KEY, AllocationBody, AvailabilityBody, LoginBody
from app.auth import Identity, current_identity, sign_in, sign_out
from app.clients.smarttt import SmartttClient, get_smarttt
from app.config import Settings, get_settings
from app.db import get_db
from app.errors import ApiError, ok
from app.services import allocation, availability, export

router = APIRouter()

Db = Annotated[Session, Depends(get_db)]
Smarttt = Annotated[SmartttClient, Depends(get_smarttt)]
Me = Annotated[Identity, Depends(current_identity)]
Cfg = Annotated[Settings, Depends(get_settings)]
TermParam = Annotated[str | None, Query(alias="term", max_length=64)]
SectionKey = Annotated[str, Path(pattern=SECTION_KEY, max_length=64)]
LecturerId = Annotated[str, Path(pattern=r"^[0-9a-fA-F-]{32,36}$")]


@router.get("/health")
def health(db: Db) -> dict[str, Any]:
    db.execute(text("SELECT 1"))
    return ok({"status": "ok"})


# -- sign-in -------------------------------------------------------------------


@router.post("/auth/login")
def login(
    body: LoginBody, request: Request, response: Response, db: Db, smarttt: Smarttt, settings: Cfg
) -> dict[str, Any]:
    identity = sign_in(db, response, request, body.identifier, body.password, smarttt, settings)
    return ok(identity.public())


@router.post("/auth/logout")
def logout(request: Request, response: Response, db: Db, settings: Cfg) -> dict[str, Any]:
    sign_out(db, request, response, settings)
    return ok(None)


@router.get("/auth/me")
def me(identity: Me) -> dict[str, Any]:
    return ok(identity.public())


# -- reference data ---------------------------------------------------------------


@router.get("/terms")
def terms(_identity: Me, smarttt: Smarttt) -> dict[str, Any]:
    return ok(smarttt.terms())


@router.get("/departments")
def departments(identity: Me, smarttt: Smarttt) -> dict[str, Any]:
    """The departments this person can see: all for the Directorate, else their own."""
    rows = smarttt.departments()
    visible = [d for d in rows if identity.can_view(int(d["id"]))]
    return ok([{**d, "role": identity.role_in(int(d["id"]))} for d in visible])


# -- a department's allocation ------------------------------------------------------


@router.get("/departments/{department_id}/sessions")
def department_sessions(
    department_id: int, identity: Me, db: Db, smarttt: Smarttt, term: TermParam = None
) -> dict[str, Any]:
    return ok(allocation.department_board(db, smarttt, identity, department_id, term))


@router.get("/departments/{department_id}/lecturers")
def department_lecturers(
    department_id: int, identity: Me, db: Db, smarttt: Smarttt, term: TermParam = None
) -> dict[str, Any]:
    return ok(availability.department_lecturers(db, smarttt, identity, department_id, term))


@router.get("/departments/{department_id}/progress")
def department_progress(
    department_id: int, identity: Me, db: Db, smarttt: Smarttt, term: TermParam = None
) -> dict[str, Any]:
    return ok(allocation.department_progress(db, smarttt, identity, department_id, term))


@router.post("/departments/{department_id}/submit")
def submit(
    department_id: int, identity: Me, db: Db, smarttt: Smarttt, term: TermParam = None
) -> dict[str, Any]:
    return ok(allocation.submit(db, smarttt, identity, department_id, term))


@router.get("/departments/{department_id}/allocations/export.pdf")
def export_pdf(
    department_id: int, identity: Me, db: Db, smarttt: Smarttt, term: TermParam = None
) -> Response:
    board = allocation.department_board(db, smarttt, identity, department_id, term)
    department = next((d for d in smarttt.departments() if int(d["id"]) == department_id), None)
    if department is None:
        raise ApiError(404, "NOT_FOUND", "No such department.")
    pdf = export.build_pdf(department, board, identity.full_name)
    filename = (
        f"allocation-{department['code']}-{board['term']['academic_year'].replace('/', '-')}"
        f"-S{board['term']['semester']}.pdf"
    )
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# -- one class ------------------------------------------------------------------------


@router.get("/sessions/{key}/free-lecturers")
def free_lecturers(
    key: SectionKey,
    identity: Me,
    db: Db,
    smarttt: Smarttt,
    term: TermParam = None,
    scope: Literal["department", "all"] = "department",
) -> dict[str, Any]:
    return ok(allocation.free_lecturers(db, smarttt, identity, key, term, scope))


@router.put("/sessions/{key}/allocation")
def put_allocation(
    key: SectionKey, body: AllocationBody, identity: Me, db: Db, smarttt: Smarttt, term: TermParam = None
) -> dict[str, Any]:
    hours = {
        "lecture_hours": body.lecture_hours,
        "practical_hours": body.practical_hours,
        "cf_hours": body.cf_hours,
    }
    return ok(
        allocation.set_allocation(
            db, smarttt, identity, key, term, body.lecturer_id, body.expected_lecturer_id, hours
        )
    )


# -- lecturers -------------------------------------------------------------------------


@router.get("/lecturers/{lecturer_id}/availability")
def get_availability(
    lecturer_id: LecturerId, identity: Me, db: Db, smarttt: Smarttt, term: TermParam = None
) -> dict[str, Any]:
    return ok(availability.get_availability(db, smarttt, identity, lecturer_id, term))


@router.put("/lecturers/{lecturer_id}/availability")
def put_availability(
    lecturer_id: LecturerId,
    body: AvailabilityBody,
    identity: Me,
    db: Db,
    smarttt: Smarttt,
    term: TermParam = None,
) -> dict[str, Any]:
    periods = [p.model_dump() for p in body.unavailable]
    return ok(availability.put_availability(db, smarttt, identity, lecturer_id, term, periods))


# -- the Directorate's overview ----------------------------------------------------------


@router.get("/progress")
def progress(identity: Me, db: Db, smarttt: Smarttt, term: TermParam = None) -> dict[str, Any]:
    return ok(allocation.all_progress(db, smarttt, identity, term))
