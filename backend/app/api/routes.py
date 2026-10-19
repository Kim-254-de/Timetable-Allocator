"""HTTP API, mounted under /api. Every response uses the {success, data} wrapper (app.errors)."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.schemas import (
    SECTION_KEY,
    AllocationBody,
    AvailabilityBody,
    BulkBody,
    FormEntryBody,
    LecturerBody,
    LecturerPatch,
    LoginBody,
)
from app.auth import Identity, current_identity, sign_in, sign_out
from app.clients.generator import GeneratorClient, get_generator
from app.clients.smarttt import SmartttClient, get_smarttt
from app.config import Settings, get_settings
from app.db import get_db
from app.errors import ApiError, ok
from app.services import allocation, availability, export, form, form_export

router = APIRouter()

Db = Annotated[Session, Depends(get_db)]
Smarttt = Annotated[SmartttClient, Depends(get_smarttt)]
Me = Annotated[Identity, Depends(current_identity)]
Generator = Annotated[GeneratorClient, Depends(get_generator)]
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


# -- the allocation form (units and groups from the Timetable Generator) --------------------

DeptCode = Annotated[str, Path(pattern=r"^[A-Za-z0-9 ._-]{1,32}$")]
EntryId = Annotated[str, Path(pattern=r"^[0-9a-fA-F-]{32,36}$")]


@router.get("/generator/terms")
def generator_terms(_identity: Me, generator: Generator) -> dict[str, Any]:
    return ok(generator.terms())


@router.get("/form/progress")
def form_progress(identity: Me, db: Db, generator: Generator, term: TermParam = None) -> dict[str, Any]:
    return ok(form.progress(db, generator, identity, term))


@router.get("/form/{department}")
def form_board(
    department: DeptCode, identity: Me, db: Db, generator: Generator, term: TermParam = None
) -> dict[str, Any]:
    return ok(form.board(db, generator, identity, department, term))


@router.put("/form/{department}/entries")
def form_save(
    department: DeptCode,
    body: FormEntryBody,
    identity: Me,
    db: Db,
    generator: Generator,
    term: TermParam = None,
) -> dict[str, Any]:
    return ok(form.save_entry(db, generator, identity, department, term, body.model_dump(exclude_unset=True)))


@router.post("/form/{department}/entries/bulk")
def form_bulk(
    department: DeptCode, body: BulkBody, identity: Me, db: Db, generator: Generator, term: TermParam = None
) -> dict[str, Any]:
    return ok(form.bulk_entries(db, generator, identity, department, term, body.rows))


@router.delete("/form/{department}/entries/{entry_id}")
def form_delete(
    department: DeptCode,
    entry_id: EntryId,
    identity: Me,
    db: Db,
    generator: Generator,
    term: TermParam = None,
) -> dict[str, Any]:
    form.delete_entry(db, generator, identity, department, term, entry_id)
    return ok(None)


@router.post("/form/{department}/submit")
def form_submit(
    department: DeptCode, identity: Me, db: Db, generator: Generator, term: TermParam = None
) -> dict[str, Any]:
    return ok(form.submit(db, generator, identity, department, term))


@router.post("/form/{department}/reopen")
def form_reopen(
    department: DeptCode, identity: Me, db: Db, generator: Generator, term: TermParam = None
) -> dict[str, Any]:
    return ok(form.reopen(db, generator, identity, department, term))


@router.get("/form/{department}/export.{fmt}")
def form_export_file(
    department: DeptCode,
    fmt: Literal["pdf", "docx", "xlsx"],
    identity: Me,
    db: Db,
    generator: Generator,
    term: TermParam = None,
) -> Response:
    board = form.board(db, generator, identity, department, term)
    submitted = board["submission"]["submitted_by"] if board["submission"] else identity.actor
    content = form_export.BUILDERS[fmt](form_export.layout(board, submitted.split(" (")[0]))
    name = "".join(ch if ch.isalnum() else "-" for ch in str(board["term"].get("name") or "term")).strip("-")
    filename = f"allocation-{form.compact(board['department']['code'])}-{name}.{fmt}"
    return Response(
        content,
        media_type=form_export.MEDIA[fmt],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# -- each department's own lecturers ---------------------------------------------------------


@router.get("/form/{department}/lecturers")
def form_lecturers(department: DeptCode, identity: Me, db: Db, generator: Generator) -> dict[str, Any]:
    ctx = form.context(generator, identity, department, None)
    show = ctx.role is not None or identity.timetabling_office
    return ok(
        [form.lecturer_dict(lec, show) for lec in form.department_lecturers(db, form.compact(department))]
    )


@router.post("/form/{department}/lecturers")
def form_add_lecturer(
    department: DeptCode, body: LecturerBody, identity: Me, db: Db, generator: Generator
) -> dict[str, Any]:
    ctx = form.context(generator, identity, department, None)
    return ok(form.lecturer_dict(form.create_lecturer(db, identity, ctx, body.model_dump())))


@router.post("/form/{department}/lecturers/bulk")
def form_bulk_lecturers(
    department: DeptCode, body: BulkBody, identity: Me, db: Db, generator: Generator
) -> dict[str, Any]:
    return ok(form.bulk_lecturers(db, generator, identity, department, body.rows))


@router.patch("/form/{department}/lecturers/{lecturer_id}")
def form_update_lecturer(
    department: DeptCode,
    lecturer_id: LecturerId,
    body: LecturerPatch,
    identity: Me,
    db: Db,
    generator: Generator,
) -> dict[str, Any]:
    ctx = form.context(generator, identity, department, None)
    lecturer = form.get_lecturer(db, lecturer_id)
    form.lecturer_ctx_check(lecturer, ctx)
    fields = body.model_dump(exclude_unset=True)
    if fields.get("max_weekly_hours") == 0:
        fields["max_weekly_hours"] = None
    return ok(form.lecturer_dict(form.update_lecturer(db, identity, ctx, lecturer, fields)))


@router.delete("/form/{department}/lecturers/{lecturer_id}")
def form_delete_lecturer(
    department: DeptCode, lecturer_id: LecturerId, identity: Me, db: Db, generator: Generator
) -> dict[str, Any]:
    ctx = form.context(generator, identity, department, None)
    lecturer = form.get_lecturer(db, lecturer_id)
    form.lecturer_ctx_check(lecturer, ctx)
    form.delete_lecturer(db, identity, ctx, lecturer)
    return ok(None)
