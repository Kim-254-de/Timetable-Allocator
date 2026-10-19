"""The allocation form's lecturers reach SMARTTT (lecturers' timetables, Smart Attendance)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import FormEntry
from tests.conftest import sign_in
from tests.fake_smarttt import COLLINS, JANE, TERM

KEYS = {"COSC103-GRA": "412-GRA", "COSC103-GRB": "412-GRB", "COSC200-MAIN": "500-MAIN"}


def _lecturer(client, name, staff):
    response = client.post(
        "/api/form/CS/lecturers", json={"full_name": name, "staff_number": staff, "phone": "07"}
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["id"]


def _save(client, unit, group="", **fields):
    return client.put("/api/form/CS/entries", json={"unit_code": unit, "group_label": group, **fields})


def _row(client, unit, group=""):
    body = client.get("/api/form/CS").json()["data"]
    return next(r for r in body["rows"] if r["unit_code"] == unit and r["group"] == group), body


@pytest.fixture
def linked(generator):
    generator.link_to_smarttt(TERM["id"], KEYS)
    return generator


def test_an_allocation_is_sent_to_smarttt_and_changes_follow(client, smarttt, linked):
    sign_in(client, "STF/0100")
    jane = _lecturer(client, "Jane Otieno", "stf/0001")
    saved = _save(client, "COSC 103", "GR A", lecturer_id=jane, lecture_hours=2)
    assert saved.status_code == 200, saved.text
    assert saved.json()["data"]["smarttt"]["state"] == "sent"
    assert smarttt.sections["412-GRA"]["lecturer"]["id"] == JANE

    collins = _lecturer(client, "Collins Mwangi", "STF/0002")
    assert _save(client, "COSC 103", "GR A", lecturer_id=collins).status_code == 200
    assert smarttt.sections["412-GRA"]["lecturer"]["id"] == COLLINS
    row, body = _row(client, "COSC 103", "GR A")
    assert row["smarttt"]["state"] == "sent" and body["summary"]["not_in_smarttt"] == 0

    # Clearing the row takes the lecturer off the class in SMARTTT too.
    assert client.delete(f"/api/form/CS/entries/{row['entry']['id']}").status_code == 200
    assert smarttt.sections["412-GRA"]["lecturer"] is None


def test_smarttt_refusing_a_clash_keeps_nothing(client, smarttt, linked, db):
    sign_in(client, "STF/0100")
    smarttt.allocate("412-GRB", JANE)  # on the earlier board: Tuesday 10:00-12:00
    jane = _lecturer(client, "Jane Otieno", "STF/0001")
    refused = _save(client, "COSC 103", "GR A", lecturer_id=jane)
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "SMARTTT_REFUSED"
    assert db.scalar(select(FormEntry).where(FormEntry.key == "COSC103-GRA")) is None


def test_a_staff_number_smarttt_does_not_know_is_refused(client, smarttt, linked):
    sign_in(client, "STF/0100")
    nobody = _lecturer(client, "New Person", "STF/9999")
    refused = _save(client, "COSC 200", lecturer_id=nobody)
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "UNKNOWN_IN_SMARTTT"


def test_while_smarttt_is_down_allocations_wait_and_are_sent_later(client, smarttt, linked):
    sign_in(client, "STF/0100")
    jane = _lecturer(client, "Jane Otieno", "STF/0001")
    smarttt.down = True
    saved = _save(client, "COSC 200", lecturer_id=jane, lecture_hours=3)
    assert saved.status_code == 200
    assert saved.json()["data"]["smarttt"]["state"] == "failed"  # kept here, not in SMARTTT yet
    _, body = _row(client, "COSC 200")
    assert body["summary"]["not_in_smarttt"] == 1

    smarttt.down = False
    sent = client.post("/api/form/CS/send-to-smarttt")
    assert sent.status_code == 200, sent.text
    assert smarttt.sections["500-MAIN"]["lecturer"]["id"] == JANE
    assert (
        next(r for r in sent.json()["data"]["rows"] if r["unit_code"] == "COSC 200")["smarttt"]["state"]
        == "sent"
    )


def test_nothing_is_sent_until_smarttt_has_the_timetable(client, smarttt, generator):
    generator.link_to_smarttt(TERM["id"], KEYS, sent=False)
    sign_in(client, "STF/0100")
    jane = _lecturer(client, "Jane Otieno", "STF/0001")
    saved = _save(client, "COSC 200", lecturer_id=jane)
    assert saved.status_code == 200
    assert saved.json()["data"]["smarttt"]["state"] == "waiting"
    assert smarttt.sections["500-MAIN"]["lecturer"] is None
    assert client.post("/api/form/CS/send-to-smarttt").status_code == 409

    generator.in_smarttt = True  # the Director's version reached SMARTTT
    assert client.post("/api/form/CS/send-to-smarttt").status_code == 200
    assert smarttt.sections["500-MAIN"]["lecturer"]["id"] == JANE


def test_lecturers_need_a_staff_number(client, smarttt, generator):
    sign_in(client, "STF/0100")
    response = client.post("/api/form/CS/lecturers", json={"full_name": "No Number"})
    assert response.status_code == 422
