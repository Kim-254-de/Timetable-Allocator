from __future__ import annotations

from tests.conftest import sign_in
from tests.test_exams import CS, ED, KEY, _course, _lecturer, _ok, _unit


def _papers(client):
    """CS has three papers; Education has a lecturer on its own list."""
    sign_in(client, "STF/0103")
    sam = _lecturer(client, ED, "Sam Mwangi", "STF/50")
    client.cookies.clear()
    sign_in(client, "STF/0100")
    course = _course(client, CS, "BSC.CS", 120)
    jane = _lecturer(client, CS, "Jane Otieno", "STF/9")
    ids = [_unit(client, CS, code, [course], lecturer=jane) for code in ("COSC 101", "COSC 102", "COSC 103")]
    papers = [_ok(client.post(f"{CS}/exam-papers", json={"unit_ids": [u]}))["id"] for u in ids]
    return papers, jane, sam


def _set(client, paper, lecturer, room=""):
    return client.put(f"{CS}/invigilators/{paper}", json={"lecturer_id": lecturer, "room": room})


def test_nothing_to_name_until_the_director_shares_a_draft(client, generator):
    papers, jane, _sam = _papers(client)
    board = _ok(client.get(f"{CS}/invigilators"))
    assert board["draft"] is None and board["can_edit"] is False
    assert _set(client, papers[0], jane).json()["error"]["code"] == "NOT_IN_DRAFT"


def test_one_person_is_never_in_two_places_in_a_session(client, generator):
    papers, jane, sam = _papers(client)
    generator.share_exams(
        {
            papers[0]: ("2026-11-23", 0, ["STB 1"]),
            papers[1]: ("2026-11-23", 0, ["STB 2"]),
            papers[2]: ("2026-11-24", 1, ["UTC 1"]),
        }
    )
    board = _ok(client.get(f"{CS}/invigilators"))
    assert board["can_edit"] is True and len(board["problems"]) == 3
    assert board["papers"][0]["rooms"] == ["STB 1"] and board["papers"][0]["start_time"] == "08:30"
    _ok(_set(client, papers[0], jane))
    busy = _set(client, papers[1], jane)
    assert busy.status_code == 409 and busy.json()["error"]["code"] == "INVIGILATOR_BUSY"
    # Someone from another department can be named (Education's Sam).
    _ok(_set(client, papers[1], sam))
    board = _ok(client.get(f"{CS}/invigilators"))
    assert board["papers"][1]["main"]["department_code"] == "ED"
    duties = {lec["display"]: lec["duties"] for lec in board["lecturers"]}
    assert duties["Dr. Jane Otieno (FT)"] == 1 and duties["Dr. Sam Mwangi (FT)"] == 1


def test_a_duty_limit_is_kept(client, generator):
    papers, jane, _sam = _papers(client)
    generator.share_exams({p: ("2026-11-23", i, ["STB 1"]) for i, p in enumerate(papers)})
    _ok(client.patch(f"{CS}/lecturers/{jane}", json={"max_exam_duties": 1}))
    _ok(_set(client, papers[0], jane))
    limited = _set(client, papers[1], jane)
    assert limited.status_code == 409 and limited.json()["error"]["code"] == "DUTY_LIMIT"


def test_the_generator_sees_invigilators_once_the_cod_publishes(client, generator):
    papers, jane, sam = _papers(client)
    generator.share_exams({p: ("2026-11-23", i, ["STB 1"]) for i, p in enumerate(papers)})
    url = "/api/integrations/generator/terms/term-1/invigilators"
    _ok(_set(client, papers[0], jane))
    _ok(_set(client, papers[1], sam))
    refused = client.post(f"{CS}/invigilators/publish")
    assert refused.status_code == 409 and "1 papers have no invigilator" in refused.json()["error"]["message"]
    assert _ok(client.get(url, headers=KEY)) == {}
    _ok(_set(client, papers[2], jane))
    board = _ok(client.post(f"{CS}/invigilators/publish"))
    assert board["published"] is True and board["can_edit"] is False
    assert _set(client, papers[2], None).status_code == 409  # locked
    data = _ok(client.get(url, headers=KEY))
    assert data[papers[1]][""] == {"staff_number": "STF/50", "name": "Dr. Sam Mwangi (FT)"}
    assert set(data) == set(papers)
    _ok(client.post(f"{CS}/invigilators/reopen"))
    assert _ok(client.get(url, headers=KEY)) == {}


def test_a_paper_in_several_rooms_needs_an_extra_invigilator_per_extra_room(client, generator):
    papers, jane, sam = _papers(client)
    sign_in(client, "STF/0100")
    tom = _lecturer(client, CS, "Tom Kariuki", "STF/10")
    generator.share_exams(
        {
            papers[0]: ("2026-11-23", 0, ["UTC 1", "STB 1", "STB 2"]),
            papers[1]: ("2026-11-23", 1, ["ADM 1"]),
            papers[2]: ("2026-11-24", 0, ["ADM 1"]),
        }
    )
    board = _ok(client.get(f"{CS}/invigilators"))
    big = board["papers"][0]
    assert big["main_room"] == "UTC 1" and [e["room"] for e in big["extras"]] == ["STB 1", "STB 2"]
    assert len(board["problems"]) == 5  # three main invigilators, two extra rooms
    _ok(_set(client, papers[0], jane))
    # The main invigilator can't also be the extra one in another room of the same paper.
    busy = _set(client, papers[0], jane, "STB 1")
    assert busy.status_code == 409 and busy.json()["error"]["code"] == "INVIGILATOR_BUSY"
    assert _set(client, papers[0], tom, "UTC 1").status_code == 422  # the main room isn't an extra room
    _ok(_set(client, papers[0], tom, "STB 1"))
    for paper in papers[1:]:
        _ok(_set(client, paper, jane))
    refused = client.post(f"{CS}/invigilators/publish")
    assert refused.status_code == 409
    assert [p["message"] for p in refused.json()["error"]["details"]["problems"]] == [
        "Name an invigilator for COSC 101 title in STB 2."
    ]
    _ok(_set(client, papers[0], sam, "STB 2"))
    _ok(client.post(f"{CS}/invigilators/publish"))
    data = _ok(client.get("/api/integrations/generator/terms/term-1/invigilators", headers=KEY))
    assert (
        set(data[papers[0]]) == {"", "STB 1", "STB 2"}
        and data[papers[0]]["STB 2"]["staff_number"] == "STF/50"
    )
    duties = {lec["display"]: lec["duties"] for lec in _ok(client.get(f"{CS}/invigilators"))["lecturers"]}
    assert duties["Dr. Jane Otieno (FT)"] == 3 and duties["Dr. Tom Kariuki (FT)"] == 1
