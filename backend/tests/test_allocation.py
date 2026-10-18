from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Allocation, AuditLog, Submission
from tests.conftest import sign_in
from tests.fake_smarttt import COLLINS, CS, EDU, JANE, OMONDI


def _put(client, key, lecturer_id, expected=None, **hours):
    return client.put(
        f"/api/sessions/{key}/allocation",
        json={"lecturer_id": lecturer_id, "expected_lecturer_id": expected, **hours},
    )


# -- the department's board --------------------------------------------------------------


def test_board_shows_owned_sections_with_servicing(client, smarttt):
    sign_in(client, "STF/0100")
    body = client.get(f"/api/departments/{CS}/sessions").json()["data"]
    assert [s["code"] for s in body["sections"]] == ["COSC 103 GR A", "COSC 103 GR B", "COSC 200"]
    assert body["sections"][0]["servicing"] is True  # taught to Education's students
    assert body["sections"][2]["servicing"] is False
    assert body["summary"] == {"sections": 3, "allocated": 0, "outstanding": 3, "conflicts": 0}
    assert body["can_submit"] is True


def test_other_departments_are_hidden(client, smarttt):
    sign_in(client, "STF/0100")
    response = client.get(f"/api/departments/{EDU}/sessions")
    assert response.status_code == 403
    departments = client.get("/api/departments").json()["data"]
    assert [d["id"] for d in departments] == [CS]


def test_director_sees_every_department_read_only(client, smarttt):
    sign_in(client, "STF/0102")
    assert len(client.get("/api/departments").json()["data"]) == 2
    board = client.get(f"/api/departments/{CS}/sessions").json()["data"]
    assert board["can_allocate"] is False
    assert _put(client, "412-GRA", JANE).status_code == 403


# -- free lecturers --------------------------------------------------------------------------


def test_free_lecturers_explain_who_is_busy(client, smarttt):
    smarttt.allocate("412-GRB", JANE)  # Jane teaches TUE 10-12 already
    sign_in(client, "STF/0100")
    body = client.get("/api/sessions/412-GRA/free-lecturers").json()["data"]
    by_name = {c["lecturer"]["full_name"]: c for c in body["candidates"]}
    assert by_name["Collins Mwangi"]["free"] is True
    assert by_name["Jane Otieno"]["free"] is False
    assert by_name["Jane Otieno"]["clashes"][0]["clashes_with"] == "COSC 103 GR B"
    assert "Omondi Achieng" not in by_name  # another department's lecturer
    everyone = client.get("/api/sessions/412-GRA/free-lecturers?scope=all").json()["data"]
    assert "Omondi Achieng" in {c["lecturer"]["full_name"] for c in everyone["candidates"]}


def test_weekly_hours_limit_is_shown(client, smarttt):
    smarttt.allocate("500-MAIN", COLLINS)  # 3 h of Collins' 4
    sign_in(client, "STF/0100")
    body = client.get("/api/sessions/412-GRA/free-lecturers").json()["data"]
    collins = next(c for c in body["candidates"] if c["lecturer"]["id"] == COLLINS)
    assert collins["over_limit"] is True
    assert collins["weekly_hours_after"] == 5.0


# -- saving --------------------------------------------------------------------------------------


def test_allocate_reaches_smarttt_and_is_recorded(client, smarttt, db: Session):
    sign_in(client, "STF/0101")  # department staff can allocate
    response = _put(client, "412-GRA", JANE, lecture_hours=30, practical_hours=15)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["section"]["lecturer"]["id"] == JANE
    assert data["section"]["allocation"]["lecture_hours"] == 30.0
    assert smarttt.sections["412-GRA"]["lecturer"]["id"] == JANE

    row = db.scalar(select(Allocation))
    assert row.smarttt_lecturer_id == JANE
    assert row.synced_to_smarttt_at is not None
    assert row.entered_by_name.startswith("Ben Staff")
    assert db.scalar(select(AuditLog.action)) == "allocation.set"


def test_double_booking_is_refused(client, smarttt):
    sign_in(client, "STF/0100")
    assert _put(client, "412-GRA", JANE).status_code == 200
    response = _put(client, "412-GRB", JANE)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "LECTURER_CLASH"
    assert smarttt.sections["412-GRB"]["lecturer"] is None


def test_stale_screen_is_refused(client, smarttt):
    sign_in(client, "STF/0100")
    _put(client, "412-GRA", JANE)
    response = _put(client, "412-GRA", COLLINS, expected=None)  # screen still showed "no lecturer"
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STALE"
    assert _put(client, "412-GRA", COLLINS, expected=JANE).status_code == 200


def test_unavailable_lecturer_is_refused(client, smarttt):
    sign_in(client, "STF/0100")
    put = client.put(
        f"/api/lecturers/{JANE}/availability",
        json={
            "unavailable": [
                {"day_of_week": "TUE", "start_time": "09:00", "end_time": "11:00", "reason": "Senate"}
            ]
        },
    )
    assert put.status_code == 200, put.text
    response = _put(client, "412-GRA", JANE)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "LECTURER_UNAVAILABLE"
    candidates = client.get("/api/sessions/412-GRA/free-lecturers").json()["data"]["candidates"]
    jane = next(c for c in candidates if c["lecturer"]["id"] == JANE)
    assert jane["unavailable"][0]["reason"] == "Senate"


def test_availability_reports_affected_classes(client, smarttt):
    smarttt.allocate("412-GRA", JANE)
    sign_in(client, "STF/0100")
    body = client.put(
        f"/api/lecturers/{JANE}/availability",
        json={"unavailable": [{"day_of_week": "TUE", "start_time": "11:00", "end_time": "13:00"}]},
    ).json()["data"]
    assert body["affected"] == ["COSC 103 GR A"]


def test_availability_validation(client, smarttt):
    sign_in(client, "STF/0100")
    url = f"/api/lecturers/{JANE}/availability"
    bad_day = client.put(
        url, json={"unavailable": [{"day_of_week": "SAT", "start_time": "09:00", "end_time": "10:00"}]}
    )
    assert bad_day.status_code == 422
    backwards = client.put(
        url, json={"unavailable": [{"day_of_week": "MON", "start_time": "10:00", "end_time": "09:00"}]}
    )
    assert backwards.status_code == 422
    assert client.put(f"/api/lecturers/{OMONDI}/availability", json={"unavailable": []}).status_code == 403


def test_cannot_allocate_another_departments_class(client, smarttt):
    sign_in(client, "STF/0100")
    assert _put(client, "900-MAIN", JANE).status_code == 403


def test_smarttt_down_is_a_clear_503(client, smarttt):
    sign_in(client, "STF/0100")
    smarttt.down = True
    response = client.get(f"/api/departments/{CS}/sessions")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SMARTTT_UNAVAILABLE"


def test_wrong_key_is_reported_as_misconfiguration(client, smarttt):
    sign_in(client, "STF/0100")
    smarttt.bad_key = True
    response = client.get(f"/api/departments/{CS}/sessions")
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "SMARTTT_MISCONFIGURED"


def test_bad_section_key_rejected_before_smarttt(client, smarttt):
    sign_in(client, "STF/0100")
    calls = len(smarttt.calls)
    assert client.get("/api/sessions/..%2Fadmin/free-lecturers").status_code in (404, 422)
    assert len(smarttt.calls) == calls


# -- submitting and progress ------------------------------------------------------------------------


def test_submit_requires_everything_allocated(client, smarttt):
    sign_in(client, "STF/0100")
    _put(client, "412-GRA", JANE)
    response = client.post(f"/api/departments/{CS}/submit")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ALLOCATION_INCOMPLETE"
    assert set(response.json()["error"]["details"]["sections"]) == {"COSC 103 GR B", "COSC 200"}


def test_submit_then_change_reopens(client, smarttt, db: Session):
    sign_in(client, "STF/0100")
    _put(client, "412-GRA", JANE)
    _put(client, "412-GRB", COLLINS)
    smarttt.lecturers[JANE]["max_weekly_teaching_hours"] = 12
    _put(client, "500-MAIN", JANE)
    response = client.post(f"/api/departments/{CS}/submit")
    assert response.status_code == 200, response.text
    assert response.json()["data"]["submission"]["is_current"] is True
    assert {a.status.value for a in db.scalars(select(Allocation))} == {"submitted"}

    _put(client, "500-MAIN", None, expected=JANE)
    db.expire_all()
    assert db.scalar(select(Submission.superseded_at)) is not None
    progress = client.get(f"/api/departments/{CS}/progress").json()["data"]
    assert progress["submission"]["is_current"] is False
    assert progress["outstanding"] == 1


def test_only_the_cod_submits(client, smarttt):
    sign_in(client, "STF/0101")
    assert client.post(f"/api/departments/{CS}/submit").status_code == 403


def test_director_progress_overview(client, smarttt):
    smarttt.allocate("412-GRA", JANE)
    sign_in(client, "STF/0102")
    body = client.get("/api/progress").json()["data"]
    rows = {r["department"]["code"]: r for r in body["departments"]}
    assert rows["CS"]["allocated"] == 1
    assert rows["CS"]["outstanding"] == 2
    assert rows["ED"]["outstanding"] == 1


def test_progress_overview_is_directorate_only(client, smarttt):
    sign_in(client, "STF/0100")
    assert client.get("/api/progress").status_code == 403


# -- export ----------------------------------------------------------------------------------------------


def test_pdf_export(client, smarttt):
    smarttt.allocate("412-GRA", JANE)
    sign_in(client, "STF/0100")
    response = client.get(f"/api/departments/{CS}/allocations/export.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert "allocation-CS-2026-2027-S1.pdf" in response.headers["content-disposition"]


def test_department_lecturers_with_load_and_availability(client, smarttt):
    smarttt.allocate("412-GRA", JANE)
    sign_in(client, "STF/0100")
    client.put(
        f"/api/lecturers/{JANE}/availability",
        json={"unavailable": [{"day_of_week": "MON", "start_time": "07:00", "end_time": "09:00"}]},
    )
    body = client.get(f"/api/departments/{CS}/lecturers").json()["data"]
    jane = next(lec for lec in body["lecturers"] if lec["id"] == JANE)
    assert jane["weekly_hours"] == 2.0
    assert jane["classes"] == ["COSC 103 GR A"]
    assert jane["unavailable"][0]["day_of_week"] == "MON"
    assert {lec["id"] for lec in body["lecturers"]} == {JANE, COLLINS}


def test_repair_publish_flags_moved_and_cleared_classes(client, smarttt):
    sign_in(client, "STF/0100")
    _put(client, "412-GRA", JANE)
    _put(client, "500-MAIN", COLLINS)
    board = client.get(f"/api/departments/{CS}/sessions").json()["data"]
    assert board["summary"]["needs_attention"] == 0

    # A new timetable version moves GR A to another room, and the lecturer on
    # COSC 200 is gone (e.g. that class was removed and re-added).
    smarttt.sections["412-GRA"]["meetings"][0]["room"] = {"id": "STB 9", "code": "STB 9", "capacity": 150}
    smarttt.allocate("500-MAIN", None)
    smarttt.calls.clear()
    board = client.get(f"/api/departments/{CS}/sessions").json()["data"]
    by_code = {s["code"]: s for s in board["sections"]}
    assert by_code["COSC 103 GR A"]["attention"] == ["time_or_room_changed"]
    assert by_code["COSC 200"]["attention"] == ["lecturer_cleared"]
    assert board["summary"]["needs_attention"] == 2

    # Re-confirming the lecturer at the new time clears the flag.
    _put(client, "412-GRA", JANE, expected=JANE)
    board = client.get(f"/api/departments/{CS}/sessions").json()["data"]
    assert {s["code"]: s["attention"] for s in board["sections"]}["COSC 103 GR A"] == []
