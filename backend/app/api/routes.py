"""HTTP API, mounted under /api. Every response uses the {success, data} wrapper (app.errors)."""

from __future__ import annotations

import hmac
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.schemas import (
    SECTION_KEY,
    AllocationBody,
    AvailabilityBody,
    BulkBody,
    CourseBody,
    CoursePatch,
    GroupPatch,
    GroupsBody,
    InvigilatorBody,
    LecturerBody,
    LecturerPatch,
    LoginBody,
    NoWrittenExamBody,
    PaperBody,
    PaperPatch,
    PracticalBody,
    UnitBody,
    UnitPatch,
)
from app.auth import Identity, current_identity, sign_in, sign_out
from app.clients.generator import GeneratorClient, get_generator
from app.clients.smarttt import SmartttClient, get_smarttt
from app.config import Settings, get_settings
from app.db import get_db
from app.errors import ApiError, ok
from app.services import (
    allocation,
    availability,
    exam_import,
    exams,
    export,
    form_export,
    invigilation,
    lecturers,
    spreadsheet,
    teaching,
    teaching_import,
)
from app.services import (
    departments as access,
)
from app.services import moderation_letter as moderation_letter_service

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


# -- Excel files -------------------------------------------------------------------------


@router.post("/spreadsheets/read")
async def read_spreadsheet(request: Request, identity: Me) -> dict[str, Any]:
    """The cells of a prepared .xlsx, sent as the raw request body, for the "Paste from Excel" dialogs."""
    content = bytearray()
    async for chunk in request.stream():
        content += chunk
        if len(content) > spreadsheet.MAX_FILE_BYTES:
            raise ApiError(413, "FILE_TOO_LARGE", spreadsheet.TOO_BIG)
    return ok(await run_in_threadpool(spreadsheet.read_workbook, bytes(content)))


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


# -- what departments enter, for a term of the Timetable Generator ----------------------------

DeptCode = Annotated[str, Path(pattern=r"^[A-Za-z0-9 ._-]{1,32}$")]
ItemId = Annotated[str, Path(pattern=r"^[0-9a-fA-F-]{32,36}$")]


def _ctx(
    identity: Identity, generator: GeneratorClient, smarttt: SmartttClient, department: str, term: str | None
) -> access.Context:
    return access.context(generator, smarttt, identity, department, term)


@router.get("/generator/terms")
def generator_terms(_identity: Me, generator: Generator) -> dict[str, Any]:
    return ok(generator.terms())


@router.get("/teaching/progress")
def teaching_progress(
    identity: Me, db: Db, generator: Generator, smarttt: Smarttt, term: TermParam = None
) -> dict[str, Any]:
    return ok(teaching.progress(db, generator, smarttt, identity, term))


@router.get("/teaching/{department}")
def teaching_board(
    department: DeptCode, identity: Me, db: Db, generator: Generator, smarttt: Smarttt, term: TermParam = None
) -> dict[str, Any]:
    return ok(teaching.board(db, generator, smarttt, identity, department, term))


@router.post("/teaching/{department}/courses")
def add_course(
    department: DeptCode,
    body: CourseBody,
    identity: Me,
    db: Db,
    generator: Generator,
    smarttt: Smarttt,
    term: TermParam = None,
) -> dict[str, Any]:
    ctx = _ctx(identity, generator, smarttt, department, term)
    return ok(teaching.course_dict(teaching.create_course(db, identity, ctx, body.model_dump())))


@router.post("/teaching/{department}/courses/bulk")
def bulk_courses(
    department: DeptCode,
    body: BulkBody,
    identity: Me,
    db: Db,
    generator: Generator,
    smarttt: Smarttt,
    term: TermParam = None,
) -> dict[str, Any]:
    ctx = _ctx(identity, generator, smarttt, department, term)
    return ok(teaching_import.bulk_courses(db, identity, ctx, body.rows))


@router.patch("/teaching/{department}/courses/{course_id}")
def change_course(
    department: DeptCode,
    course_id: ItemId,
    body: CoursePatch,
    identity: Me,
    db: Db,
    generator: Generator,
    smarttt: Smarttt,
    term: TermParam = None,
) -> dict[str, Any]:
    ctx = _ctx(identity, generator, smarttt, department, term)
    fields = body.model_dump(exclude_unset=True)
    return ok(teaching.course_dict(teaching.update_course(db, identity, ctx, course_id, fields)))


@router.delete("/teaching/{department}/courses/{course_id}")
def remove_course(
    department: DeptCode,
    course_id: ItemId,
    identity: Me,
    db: Db,
    generator: Generator,
    smarttt: Smarttt,
    term: TermParam = None,
) -> dict[str, Any]:
    teaching.delete_course(db, identity, _ctx(identity, generator, smarttt, department, term), course_id)
    return ok(None)


@router.post("/teaching/{department}/units")
def add_unit(
    department: DeptCode,
    body: UnitBody,
    identity: Me,
    db: Db,
    generator: Generator,
    smarttt: Smarttt,
    term: TermParam = None,
) -> dict[str, Any]:
    ctx = _ctx(identity, generator, smarttt, department, term)
    unit = teaching.create_unit(db, identity, ctx, body.model_dump())
    return ok({"id": str(unit.id), "code": unit.code})


@router.post("/teaching/{department}/units/bulk")
def bulk_units(
    department: DeptCode,
    body: BulkBody,
    identity: Me,
    db: Db,
    generator: Generator,
    smarttt: Smarttt,
    term: TermParam = None,
) -> dict[str, Any]:
    ctx = _ctx(identity, generator, smarttt, department, term)
    return ok(teaching_import.bulk_units(db, identity, ctx, body.rows))


@router.patch("/teaching/{department}/units/{unit_id}")
def change_unit(
    department: DeptCode,
    unit_id: ItemId,
    body: UnitPatch,
    identity: Me,
    db: Db,
    generator: Generator,
    smarttt: Smarttt,
    term: TermParam = None,
) -> dict[str, Any]:
    ctx = _ctx(identity, generator, smarttt, department, term)
    unit = teaching.update_unit(db, identity, ctx, unit_id, body.model_dump(exclude_unset=True))
    return ok({"id": str(unit.id), "code": unit.code})


@router.delete("/teaching/{department}/units/{unit_id}")
def remove_unit(
    department: DeptCode,
    unit_id: ItemId,
    identity: Me,
    db: Db,
    generator: Generator,
    smarttt: Smarttt,
    term: TermParam = None,
) -> dict[str, Any]:
    teaching.delete_unit(db, identity, _ctx(identity, generator, smarttt, department, term), unit_id)
    return ok(None)


@router.put("/teaching/{department}/units/{unit_id}/groups")
def put_groups(
    department: DeptCode,
    unit_id: ItemId,
    body: GroupsBody,
    identity: Me,
    db: Db,
    generator: Generator,
    smarttt: Smarttt,
    term: TermParam = None,
) -> dict[str, Any]:
    ctx = _ctx(identity, generator, smarttt, department, term)
    groups = [g.model_dump(exclude_unset=True) for g in body.groups]
    unit = teaching.set_groups(db, identity, ctx, unit_id, groups)
    return ok({"id": str(unit.id), "groups": len(unit.groups)})


@router.post("/teaching/{department}/groups/bulk")
def bulk_groups(
    department: DeptCode,
    body: BulkBody,
    identity: Me,
    db: Db,
    generator: Generator,
    smarttt: Smarttt,
    term: TermParam = None,
) -> dict[str, Any]:
    ctx = _ctx(identity, generator, smarttt, department, term)
    return ok(teaching_import.bulk_groups(db, identity, ctx, body.rows))


@router.patch("/teaching/{department}/groups/{group_id}")
def change_group(
    department: DeptCode,
    group_id: ItemId,
    body: GroupPatch,
    identity: Me,
    db: Db,
    generator: Generator,
    smarttt: Smarttt,
    term: TermParam = None,
) -> dict[str, Any]:
    ctx = _ctx(identity, generator, smarttt, department, term)
    group = teaching.update_group(db, identity, ctx, group_id, body.model_dump(exclude_unset=True))
    return ok({"id": str(group.id)})


@router.post("/teaching/{department}/publish")
def publish(
    department: DeptCode, identity: Me, db: Db, generator: Generator, smarttt: Smarttt, term: TermParam = None
) -> dict[str, Any]:
    return ok(teaching.publish(db, generator, smarttt, identity, department, term))


@router.post("/teaching/{department}/reopen")
def reopen(
    department: DeptCode, identity: Me, db: Db, generator: Generator, smarttt: Smarttt, term: TermParam = None
) -> dict[str, Any]:
    return ok(teaching.reopen(db, generator, smarttt, identity, department, term))


@router.get("/teaching/{department}/export.{fmt}")
def teaching_export(
    department: DeptCode,
    fmt: Literal["pdf", "docx", "xlsx"],
    identity: Me,
    db: Db,
    generator: Generator,
    smarttt: Smarttt,
    term: TermParam = None,
) -> Response:
    board = teaching.board(db, generator, smarttt, identity, department, term)
    publication = board["publication"]
    prepared_by = str(publication["published_by"] if publication else identity.actor)
    content = form_export.BUILDERS[fmt](form_export.layout(board, prepared_by.split(" (")[0]))
    name = "".join(ch if ch.isalnum() else "-" for ch in str(board["term"].get("name") or "term")).strip("-")
    filename = f"allocation-{access.compact(board['department']['code'])}-{name}.{fmt}"
    return Response(
        content,
        media_type=form_export.MEDIA[fmt],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# -- exams: papers, practicals, the moderation letter -------------------------------------------


@router.get("/teaching/{department}/exams")
def exam_board(
    department: DeptCode, identity: Me, db: Db, generator: Generator, smarttt: Smarttt, term: TermParam = None
) -> dict[str, Any]:
    return ok(exams.board(db, generator, smarttt, identity, department, term))


@router.post("/teaching/{department}/exam-papers")
def add_paper(
    department: DeptCode,
    body: PaperBody,
    identity: Me,
    db: Db,
    generator: Generator,
    smarttt: Smarttt,
    term: TermParam = None,
) -> dict[str, Any]:
    ctx = _ctx(identity, generator, smarttt, department, term)
    return ok({"id": str(exams.create_paper(db, identity, ctx, body.model_dump()).id)})


@router.post("/teaching/{department}/exam-papers/from-units")
def papers_from_units(
    department: DeptCode, identity: Me, db: Db, generator: Generator, smarttt: Smarttt, term: TermParam = None
) -> dict[str, Any]:
    return ok(exams.start_from_units(db, identity, _ctx(identity, generator, smarttt, department, term)))


@router.post("/teaching/{department}/exam-papers/bulk")
def bulk_papers(
    department: DeptCode,
    body: BulkBody,
    identity: Me,
    db: Db,
    generator: Generator,
    smarttt: Smarttt,
    term: TermParam = None,
) -> dict[str, Any]:
    ctx = _ctx(identity, generator, smarttt, department, term)
    return ok(exam_import.bulk_papers(db, identity, ctx, body.rows))


@router.patch("/teaching/{department}/exam-papers/{paper_id}")
def change_paper(
    department: DeptCode,
    paper_id: ItemId,
    body: PaperPatch,
    identity: Me,
    db: Db,
    generator: Generator,
    smarttt: Smarttt,
    term: TermParam = None,
) -> dict[str, Any]:
    ctx = _ctx(identity, generator, smarttt, department, term)
    paper = exams.update_paper(db, identity, ctx, paper_id, body.model_dump(exclude_unset=True))
    return ok({"id": str(paper.id)})


@router.delete("/teaching/{department}/exam-papers/{paper_id}")
def remove_paper(
    department: DeptCode,
    paper_id: ItemId,
    identity: Me,
    db: Db,
    generator: Generator,
    smarttt: Smarttt,
    term: TermParam = None,
) -> dict[str, Any]:
    exams.delete_paper(db, identity, _ctx(identity, generator, smarttt, department, term), paper_id)
    return ok(None)


@router.put("/teaching/{department}/units/{unit_id}/no-written-exam")
def no_written_exam(
    department: DeptCode,
    unit_id: ItemId,
    body: NoWrittenExamBody,
    identity: Me,
    db: Db,
    generator: Generator,
    smarttt: Smarttt,
    term: TermParam = None,
) -> dict[str, Any]:
    ctx = _ctx(identity, generator, smarttt, department, term)
    exams.set_no_written_exam(db, identity, ctx, unit_id, body.no_written_exam)
    return ok(None)


@router.post("/teaching/{department}/practicals")
def add_practical(
    department: DeptCode,
    body: PracticalBody,
    identity: Me,
    db: Db,
    generator: Generator,
    smarttt: Smarttt,
    term: TermParam = None,
) -> dict[str, Any]:
    ctx = _ctx(identity, generator, smarttt, department, term)
    return ok({"id": str(exams.save_practical(db, identity, ctx, None, body.model_dump()).id)})


@router.post("/teaching/{department}/practicals/bulk")
def bulk_practicals(
    department: DeptCode,
    body: BulkBody,
    identity: Me,
    db: Db,
    generator: Generator,
    smarttt: Smarttt,
    term: TermParam = None,
) -> dict[str, Any]:
    ctx = _ctx(identity, generator, smarttt, department, term)
    return ok(exam_import.bulk_practicals(db, identity, ctx, body.rows))


@router.put("/teaching/{department}/practicals/{practical_id}")
def change_practical(
    department: DeptCode,
    practical_id: ItemId,
    body: PracticalBody,
    identity: Me,
    db: Db,
    generator: Generator,
    smarttt: Smarttt,
    term: TermParam = None,
) -> dict[str, Any]:
    ctx = _ctx(identity, generator, smarttt, department, term)
    return ok({"id": str(exams.save_practical(db, identity, ctx, practical_id, body.model_dump()).id)})


@router.delete("/teaching/{department}/practicals/{practical_id}")
def remove_practical(
    department: DeptCode,
    practical_id: ItemId,
    identity: Me,
    db: Db,
    generator: Generator,
    smarttt: Smarttt,
    term: TermParam = None,
) -> dict[str, Any]:
    exams.delete_practical(db, identity, _ctx(identity, generator, smarttt, department, term), practical_id)
    return ok(None)


@router.post("/teaching/{department}/exams/publish")
def publish_exams(
    department: DeptCode, identity: Me, db: Db, generator: Generator, smarttt: Smarttt, term: TermParam = None
) -> dict[str, Any]:
    return ok(exams.publish(db, generator, smarttt, identity, department, term))


@router.post("/teaching/{department}/exams/reopen")
def reopen_exams(
    department: DeptCode, identity: Me, db: Db, generator: Generator, smarttt: Smarttt, term: TermParam = None
) -> dict[str, Any]:
    return ok(exams.reopen(db, generator, smarttt, identity, department, term))


@router.get("/teaching/{department}/moderation-letter.{fmt}")
def moderation_letter(
    department: DeptCode,
    fmt: Literal["docx", "pdf"],
    identity: Me,
    db: Db,
    generator: Generator,
    smarttt: Smarttt,
    term: TermParam = None,
    moderator: Annotated[str, Query(max_length=1000)] = "",
    letter_date: Annotated[str, Query(alias="date", max_length=40)] = "",
) -> Response:
    """The letter sent with the department's exam drafts. `moderator`: name and address, a line each."""
    board = exams.board(db, generator, smarttt, identity, department, term)
    letter = moderation_letter_service.Letter(
        department=board["department"]["name"],
        term=str(board["term"].get("name") or ""),
        date=letter_date or date.today().strftime("%d %B %Y"),
        moderator=[line.strip() for line in moderator.splitlines() if line.strip()]
        or ["The External Moderator"],
        papers=[(p["codes"], p["title"]) for p in board["papers"]],
        cod=identity.full_name,
    )
    filename = f"moderation-letter-{access.compact(board['department']['code'])}.{fmt}"
    return Response(
        moderation_letter_service.BUILDERS[fmt](letter),
        media_type=moderation_letter_service.MEDIA[fmt],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# -- invigilators, on the Director's shared exam draft -------------------------------------------


@router.get("/teaching/{department}/invigilators")
def invigilator_board(
    department: DeptCode, identity: Me, db: Db, generator: Generator, smarttt: Smarttt, term: TermParam = None
) -> dict[str, Any]:
    return ok(invigilation.board(db, generator, smarttt, identity, department, term))


@router.put("/teaching/{department}/invigilators/{paper_id}")
def set_invigilator(
    department: DeptCode,
    paper_id: ItemId,
    body: InvigilatorBody,
    identity: Me,
    db: Db,
    generator: Generator,
    smarttt: Smarttt,
    term: TermParam = None,
) -> dict[str, Any]:
    ctx = _ctx(identity, generator, smarttt, department, term)
    return ok(invigilation.set_invigilator(db, generator, identity, ctx, paper_id, body.lecturer_id))


@router.post("/teaching/{department}/invigilators/publish")
def publish_invigilators(
    department: DeptCode, identity: Me, db: Db, generator: Generator, smarttt: Smarttt, term: TermParam = None
) -> dict[str, Any]:
    return ok(invigilation.publish(db, generator, smarttt, identity, department, term))


@router.post("/teaching/{department}/invigilators/reopen")
def reopen_invigilators(
    department: DeptCode, identity: Me, db: Db, generator: Generator, smarttt: Smarttt, term: TermParam = None
) -> dict[str, Any]:
    return ok(invigilation.reopen(db, generator, smarttt, identity, department, term))


# -- each department's own lecturers ---------------------------------------------------------


@router.get("/teaching/{department}/lecturers")
def list_lecturers(
    department: DeptCode, identity: Me, db: Db, generator: Generator, smarttt: Smarttt
) -> dict[str, Any]:
    ctx = _ctx(identity, generator, smarttt, department, None)
    show = ctx.role is not None or identity.timetabling_office
    return ok([lecturers.lecturer_dict(lec, show) for lec in lecturers.department_lecturers(db, ctx.code)])


@router.post("/teaching/{department}/lecturers")
def add_lecturer(
    department: DeptCode, body: LecturerBody, identity: Me, db: Db, generator: Generator, smarttt: Smarttt
) -> dict[str, Any]:
    ctx = _ctx(identity, generator, smarttt, department, None)
    return ok(lecturers.lecturer_dict(lecturers.create_lecturer(db, identity, ctx, body.model_dump())))


@router.post("/teaching/{department}/lecturers/bulk")
def bulk_lecturers(
    department: DeptCode, body: BulkBody, identity: Me, db: Db, generator: Generator, smarttt: Smarttt
) -> dict[str, Any]:
    ctx = _ctx(identity, generator, smarttt, department, None)
    return ok(lecturers.bulk_lecturers(db, identity, ctx, body.rows))


@router.patch("/teaching/{department}/lecturers/{lecturer_id}")
def change_lecturer(
    department: DeptCode,
    lecturer_id: LecturerId,
    body: LecturerPatch,
    identity: Me,
    db: Db,
    generator: Generator,
    smarttt: Smarttt,
) -> dict[str, Any]:
    ctx = _ctx(identity, generator, smarttt, department, None)
    lecturer = lecturers.get_lecturer(db, lecturer_id)
    lecturers.lecturer_ctx_check(lecturer, ctx)
    fields = body.model_dump(exclude_unset=True)
    for limit in ("max_weekly_hours", "max_exam_duties"):
        if fields.get(limit) == 0:  # 0 clears a limit
            fields[limit] = None
    return ok(lecturers.lecturer_dict(lecturers.update_lecturer(db, identity, ctx, lecturer, fields)))


@router.delete("/teaching/{department}/lecturers/{lecturer_id}")
def remove_lecturer(
    department: DeptCode,
    lecturer_id: LecturerId,
    identity: Me,
    db: Db,
    generator: Generator,
    smarttt: Smarttt,
) -> dict[str, Any]:
    ctx = _ctx(identity, generator, smarttt, department, None)
    lecturer = lecturers.get_lecturer(db, lecturer_id)
    lecturers.lecturer_ctx_check(lecturer, ctx)
    lecturers.delete_lecturer(db, identity, ctx, lecturer)
    return ok(None)


# -- for the Timetable Generator ---------------------------------------------------------------


def require_generator_key(request: Request, settings: Cfg) -> None:
    """Fails closed: with GENERATOR_INBOUND_KEY unset, every request is refused."""
    expected = settings.generator_inbound_key
    presented = request.headers.get("X-API-Key", "")
    if not expected or not hmac.compare_digest(presented.encode(), expected.encode()):
        raise ApiError(401, "INVALID_API_KEY", "A valid X-API-Key header is required.")


@router.get(
    "/integrations/generator/terms/{term_id}/submissions",
    dependencies=[Depends(require_generator_key)],
)
def generator_submissions(
    term_id: Annotated[str, Path(max_length=64)], db: Db, smarttt: Smarttt
) -> dict[str, Any]:
    """What each department has published for the term, and which haven't, for the Director's import."""
    return ok(teaching.submissions(db, smarttt, term_id))


@router.get(
    "/integrations/generator/terms/{term_id}/exams",
    dependencies=[Depends(require_generator_key)],
)
def generator_exams(term_id: Annotated[str, Path(max_length=64)], db: Db, smarttt: Smarttt) -> dict[str, Any]:
    """Each department's published exam papers (with the class rows sitting them) and practicals."""
    return ok(exams.submissions(db, smarttt, term_id))


@router.get(
    "/integrations/generator/terms/{term_id}/invigilators",
    dependencies=[Depends(require_generator_key)],
)
def generator_invigilators(term_id: Annotated[str, Path(max_length=64)], db: Db) -> dict[str, Any]:
    """Each paper's invigilator, from departments that published theirs."""
    return ok(invigilation.for_generator(db, term_id))
