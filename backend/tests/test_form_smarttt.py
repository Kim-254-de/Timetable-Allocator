"""Submitting the allocation form publishes it to SMARTTT (lecturers' timetables, Smart Attendance)."""

from __future__ import annotations

import pytest

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
    response = client.put("/api/form/CS/entries", json={"unit_code": unit, "group_label": group, **fields})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _submit(client):
    response = client.post("/api/form/CS/submit")
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _row(board, unit, group=""):
    return next(r for r in board["rows"] if r["unit_code"] == unit and r["group"] == group)


@pytest.fixture
def linked(generator):
    generator.link_to_smarttt(TERM["id"], KEYS)
    return generator


def test_saving_stays_here_and_submitting_publishes(client, smarttt, linked):
    sign_in(client, "STF/0100")  # the COD
    jane = _lecturer(client, "Jane Otieno", "stf/0001")
    saved = _save(client, "COSC 103", "GR A", lecturer_id=jane, lecture_hours=2)
    assert saved["smarttt"]["state"] == "pending"
    assert smarttt.sections["412-GRA"]["lecturer"] is None  # not published yet

    board = _submit(client)
    assert _row(board, "COSC 103", "GR A")["smarttt"]["state"] == "sent"
    assert smarttt.sections["412-GRA"]["lecturer"]["id"] == JANE
    assert board["summary"]["not_in_smarttt"] == 0
    # A class never allocated here is left as SMARTTT has it.
    assert smarttt.sections["500-MAIN"]["lecturer"] is None


def test_changes_after_reopening_reach_smarttt_on_the_next_submit(client, smarttt, linked):
    sign_in(client, "STF/0100")
    jane = _lecturer(client, "Jane Otieno", "STF/0001")
    collins = _lecturer(client, "Collins Mwangi", "STF/0002")
    _save(client, "COSC 103", "GR A", lecturer_id=jane)
    _save(client, "COSC 200", lecturer_id=jane)
    _submit(client)
    assert client.post("/api/form/CS/reopen").status_code == 200

    _save(client, "COSC 103", "GR A", lecturer_id=collins)
    cosc200 = _row(client.get("/api/form/CS").json()["data"], "COSC 200")
    assert client.delete(f"/api/form/CS/entries/{cosc200['entry']['id']}").status_code == 200
    assert smarttt.sections["412-GRA"]["lecturer"]["id"] == JANE  # SMARTTT keeps the published one meanwhile

    _submit(client)
    assert smarttt.sections["412-GRA"]["lecturer"]["id"] == COLLINS
    assert smarttt.sections["500-MAIN"]["lecturer"] is None  # cleared here, so taken off there


def test_a_class_smarttt_refuses_shows_why(client, smarttt, linked):
    sign_in(client, "STF/0100")
    smarttt.allocate("412-GRB", JANE)  # given in SMARTTT's own allocation: Tuesday 10:00-12:00
    jane = _lecturer(client, "Jane Otieno", "STF/0001")
    _save(client, "COSC 103", "GR A", lecturer_id=jane)
    board = _submit(client)
    row = _row(board, "COSC 103", "GR A")
    assert row["smarttt"]["state"] == "failed" and row["smarttt"]["message"]
    assert board["summary"]["not_in_smarttt"] == 1
    assert smarttt.sections["412-GRA"]["lecturer"] is None


def test_smarttt_down_at_submit_then_publish_again(client, smarttt, linked):
    sign_in(client, "STF/0100")
    jane = _lecturer(client, "Jane Otieno", "STF/0001")
    _save(client, "COSC 200", lecturer_id=jane, lecture_hours=3)
    smarttt.down = True
    board = _submit(client)  # the submission stands
    assert board["submission"] is not None
    assert _row(board, "COSC 200")["smarttt"]["state"] == "failed"

    smarttt.down = False
    again = client.post("/api/form/CS/publish-again")
    assert again.status_code == 200, again.text
    assert _row(again.json()["data"], "COSC 200")["smarttt"]["state"] == "sent"
    assert smarttt.sections["500-MAIN"]["lecturer"]["id"] == JANE


def test_nothing_is_published_until_smarttt_has_the_timetable(client, smarttt, generator):
    generator.link_to_smarttt(TERM["id"], KEYS, sent=False)
    sign_in(client, "STF/0100")
    jane = _lecturer(client, "Jane Otieno", "STF/0001")
    _save(client, "COSC 200", lecturer_id=jane)
    board = _submit(client)
    assert _row(board, "COSC 200")["smarttt"]["state"] == "waiting"
    assert smarttt.sections["500-MAIN"]["lecturer"] is None
    assert client.post("/api/form/CS/publish-again").status_code == 409

    generator.in_smarttt = True  # the Director's version reached SMARTTT
    assert client.post("/api/form/CS/publish-again").status_code == 200
    assert smarttt.sections["500-MAIN"]["lecturer"]["id"] == JANE


def test_submit_needs_staff_numbers_smarttt_knows(client, smarttt, linked):
    sign_in(client, "STF/0100")
    pasted = client.post(
        "/api/form/CS/entries/bulk",
        json={"rows": [{"course_code": "COSC 200", "lecturer": "Dr. New Person (FT)", "l": "3"}]},
    )
    assert (
        pasted.status_code == 200 and pasted.json()["data"]["created"] == 1
    )  # pasted without a staff number
    refused = client.post("/api/form/CS/submit")
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "NO_STAFF_NUMBER"

    assert client.post("/api/form/CS/lecturers", json={"full_name": "No Number"}).status_code == 422


def test_only_the_cod_publishes_again(client, smarttt, linked):
    sign_in(client, "STF/0101")  # an editor
    assert client.post("/api/form/CS/publish-again").status_code == 403
