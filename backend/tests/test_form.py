from __future__ import annotations

from sqlalchemy import select

from app.models import FormEntry, Lecturer
from tests.conftest import sign_in


def _add_lecturer(client, name, **extra):
    response = client.post("/api/form/CS/lecturers", json={"full_name": name, "title": "Dr.", **extra})
    assert response.status_code == 200, response.text
    return response.json()["data"]["id"]


def _save(client, unit, group="", **fields):
    return client.put("/api/form/CS/entries", json={"unit_code": unit, "group_label": group, **fields})


def test_board_lists_the_departments_units_from_the_generator(client, generator):
    sign_in(client, "STF/0100")
    body = client.get("/api/form/CS").json()["data"]
    assert [(r["unit_code"], r["group"]) for r in body["rows"]] == [
        ("COSC 103", "GR A"),
        ("COSC 103", "GR B"),
        ("COSC 200", ""),
    ]
    assert body["rows"][1]["servicing"] is True  # Education's students
    assert body["rows"][0]["servicing"] is False
    assert body["can_edit"] is True and body["can_submit"] is True


def test_other_departments_forms_are_closed(client, generator):
    sign_in(client, "STF/0100")
    assert client.get("/api/form/ED").status_code == 403
    response = _save(client, "EDFO 111", lecture_hours=3)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NOT_YOUR_UNIT"


def test_allocate_and_refuse_a_clash(client, generator, db):
    sign_in(client, "STF/0101")  # an editor
    jane = _add_lecturer(client, "Jane Otieno", staff_number="stf/9", phone="0700")
    assert _save(client, "COSC 103", "GR A", lecturer_id=jane, lecture_hours=2, cf_hours=3).status_code == 200
    clash = _save(client, "COSC 103", "GR B", lecturer_id=jane)
    assert clash.status_code == 409
    assert "already teaches COSC 103 GR A" in clash.json()["error"]["message"]
    assert _save(client, "COSC 200", lecturer_id=jane).status_code == 200
    entry = db.scalar(select(FormEntry).where(FormEntry.key == "COSC103-GRA"))
    assert entry is not None and float(entry.cf_hours) == 3
    assert db.scalar(select(Lecturer)).staff_number == "STF/9"


def test_split_unit_needs_its_group_and_new_units_need_a_title(client, generator):
    sign_in(client, "STF/0100")
    assert _save(client, "COSC 103").json()["error"]["code"] == "GROUP_REQUIRED"
    assert _save(client, "COSC 499").status_code == 422
    added = _save(client, "COSC 499", unit_title="Project", lecture_hours=1)
    assert added.status_code == 200
    assert added.json()["data"]["in_timetable"] is False


def test_bulk_paste_adds_lecturers_and_rows(client, generator, db):
    sign_in(client, "STF/0100")
    rows = [
        {"Course code": "COSC 103 Group A", "L": "3", "CF": "3", "Lecturer": "Dr. Joseph Omollo (PT)"},
        {"Course code": "COSC 200", "Lecturer": "Joseph Omollo"},
        {"Course code": "COSC 999"},
    ]
    body = client.post("/api/form/CS/entries/bulk", json={"rows": rows}).json()["data"]
    assert body["created"] == 2 and body["lecturers_added"] == 1
    assert body["errors"][0]["line"] == 3
    lecturer = db.scalar(select(Lecturer))
    assert lecturer.full_name == "Joseph Omollo" and lecturer.employment_type.value == "part_time"


def test_submit_locks_until_reopened_and_downloads_work(client, generator):
    sign_in(client, "STF/0100")
    jane = _add_lecturer(client, "Jane Otieno")
    _save(client, "COSC 200", lecturer_id=jane, lecture_hours=3)
    assert client.post("/api/form/CS/submit").status_code == 200
    assert _save(client, "COSC 103", "GR A", lecturer_id=jane).json()["error"]["code"] == "FORM_SUBMITTED"
    for fmt, magic in (("pdf", b"%PDF"), ("docx", b"PK"), ("xlsx", b"PK")):
        response = client.get(f"/api/form/CS/export.{fmt}")
        assert response.status_code == 200 and response.content.startswith(magic)
    assert client.post("/api/form/CS/reopen").status_code == 200
    assert _save(client, "COSC 103", "GR A", lecturer_id=jane).status_code == 200


def test_editors_cannot_submit_and_director_sees_progress(client, generator):
    sign_in(client, "STF/0101")
    assert client.post("/api/form/CS/submit").status_code == 403
    client.post("/api/auth/logout")
    client.headers.pop("X-XSRF-TOKEN", None)
    sign_in(client, "STF/0102")
    progress = client.get("/api/form/progress").json()["data"]
    assert {d["code"] for d in progress["departments"]} == {"CS", "ED"}
    assert client.get("/api/form/CS").json()["data"]["can_edit"] is False
