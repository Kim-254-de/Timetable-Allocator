"""
An in-memory SMARTTT speaking the Allocator integration contract
(/api/v1/integrations/allocator/), mounted as an httpx transport. It applies
the same rules SMARTTT does on a lecturer PATCH (clash, weekly hours, stale
expected lecturer), so tests exercise the real round trip.
"""

from __future__ import annotations

import copy
import json
from typing import Any
from urllib.parse import unquote

import httpx

PREFIX = "/api/v1/integrations/allocator"
API_KEY = "test-allocator-key"

TERM = {
    "id": "11111111-1111-1111-1111-111111111111",
    "academic_year": "2026/2027",
    "semester": 1,
    "start_date": "2026-09-21",
    "end_date": "2026-12-18",
    "is_current": True,
}

CS, EDU = 1, 2
JANE = "aaaaaaaa-0000-0000-0000-000000000001"
COLLINS = "aaaaaaaa-0000-0000-0000-000000000002"
OMONDI = "aaaaaaaa-0000-0000-0000-000000000003"  # Education lecturer
COD_ACCOUNT = "cccccccc-0000-0000-0000-000000000001"
STAFF_ACCOUNT = "cccccccc-0000-0000-0000-000000000002"
DIRECTOR_ACCOUNT = "cccccccc-0000-0000-0000-000000000003"
EDU_COD_ACCOUNT = "cccccccc-0000-0000-0000-000000000004"


def _minutes(a: str, b: str) -> int:
    ah, am = map(int, a.split(":"))
    bh, bm = map(int, b.split(":"))
    return (bh * 60 + bm) - (ah * 60 + am)


def _overlap(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return bool(
        a["day_of_week"] == b["day_of_week"]
        and a["start_time"] < b["end_time"]
        and b["start_time"] < a["end_time"]
    )


def _section(
    key: str,
    code: str,
    unit_id: int,
    dept: int,
    meetings: list[tuple[str, str, str, str]],
    group: str | None = None,
    rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "code": code,
        "group": group,
        "unit": {
            "id": unit_id,
            "code": code.split(" GR")[0],
            "name": f"Unit {code}",
            "credit_hours": 3.0,
            "department_id": dept,
        },
        "class_rows": rows
        or [
            {
                "program_id": 10,
                "program_code": "BSC.COMP SCI",
                "program_name": "BSc CS",
                "program_department_id": CS,
                "year_of_study": 1,
                "study_semester": 1,
                "stream": "",
            }
        ],
        "meetings": [
            {
                "day_of_week": d,
                "start_time": s,
                "end_time": e,
                "room": {"id": r, "code": r, "capacity": 150},
                "session_key": None,
            }
            for d, s, e, r in meetings
        ],
        "lecturer": None,
        "lecturer_conflict": False,
        "lecturer_name_text": "",
        "session_keys": [],
        "weekly_hours": round(sum(_minutes(s, e) for _d, s, e, _r in meetings) / 60, 2),
        "registered_students": 40,
    }


class FakeSmarttt:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.down = False
        self.bad_key = False
        self.departments = [
            {"id": CS, "code": "CS", "name": "Computer Science", "faculty": "Science", "cod": None},
            {"id": EDU, "code": "ED", "name": "Education", "faculty": "Education", "cod": None},
        ]
        self.lecturers: dict[str, dict[str, Any]] = {
            JANE: self._lecturer(JANE, "STF/0001", "Jane Otieno", CS, "full_time", 12),
            COLLINS: self._lecturer(COLLINS, "STF/0002", "Collins Mwangi", CS, "part_time", 4),
            OMONDI: self._lecturer(OMONDI, "STF/0003", "Omondi Achieng", EDU, "full_time", 12),
        }
        servicing_rows = [
            {
                "program_id": 20,
                "program_code": "BED.MATH/CHEM",
                "program_name": "BEd",
                "program_department_id": EDU,
                "year_of_study": 1,
                "study_semester": 1,
                "stream": "",
            }
        ]
        self.sections: dict[str, dict[str, Any]] = {
            s["key"]: s
            for s in [
                _section(
                    "412-GRA",
                    "COSC 103 GR A",
                    412,
                    CS,
                    [("TUE", "10:00", "12:00", "STB 1")],
                    "GR A",
                    servicing_rows,
                ),
                _section(
                    "412-GRB",
                    "COSC 103 GR B",
                    412,
                    CS,
                    [("TUE", "10:00", "12:00", "STB 2")],
                    "GR B",
                    servicing_rows,
                ),
                _section(
                    "500-MAIN",
                    "COSC 200",
                    500,
                    CS,
                    [("WED", "08:00", "10:00", "UTC 1"), ("FRI", "14:00", "15:00", "UTC 1")],
                ),
                _section("900-MAIN", "EDFO 111", 900, EDU, [("MON", "08:00", "10:00", "ED 1")]),
            ]
        }
        cs_role = {"id": CS, "code": "CS", "name": "Computer Science", "faculty": "Science"}
        edu_role = {"id": EDU, "code": "ED", "name": "Education", "faculty": "Education"}
        self.identities: dict[str, dict[str, Any]] = {
            COD_ACCOUNT: self._identity(COD_ACCOUNT, "STF/0100", "Ann Cod", [{**cs_role, "role": "cod"}]),
            STAFF_ACCOUNT: self._identity(
                STAFF_ACCOUNT, "STF/0101", "Ben Staff", [{**cs_role, "role": "editor"}]
            ),
            DIRECTOR_ACCOUNT: self._identity(DIRECTOR_ACCOUNT, "STF/0102", "Dee Director", [], office=True),
            EDU_COD_ACCOUNT: self._identity(
                EDU_COD_ACCOUNT, "STF/0103", "Eve EduCod", [{**edu_role, "role": "cod"}]
            ),
        }
        self.passwords = {
            "STF/0100": COD_ACCOUNT,
            "STF/0101": STAFF_ACCOUNT,
            "STF/0102": DIRECTOR_ACCOUNT,
            "STF/0103": EDU_COD_ACCOUNT,
        }
        self.lecturer_only_password = "STF/0001"

    @staticmethod
    def _lecturer(lid: str, staff: str, name: str, dept: int, kind: str, max_hours: int) -> dict[str, Any]:
        return {
            "id": lid,
            "staff_number": staff,
            "full_name": name,
            "title": "Dr.",
            "employment_type": kind,
            "max_weekly_teaching_hours": max_hours,
            "department": {"id": dept, "code": "X", "name": "X"},
            "is_active": True,
        }

    @staticmethod
    def _identity(
        aid: str, staff: str, name: str, departments: list[dict[str, Any]], office: bool = False
    ) -> dict[str, Any]:
        return {
            "account": {
                "id": aid,
                "role": "lecturer",
                "university_id": staff,
                "email": None,
                "full_name": name,
                "is_active": True,
            },
            "timetabling_office": office,
            "departments": departments,
        }

    # -- the lecturer's week, as SMARTTT computes it ---------------------------------

    def meetings_of(self, lecturer_id: str, exclude: str | None = None) -> list[dict[str, Any]]:
        result = []
        for s in self.sections.values():
            if (s["lecturer"] or {}).get("id") != lecturer_id or s["key"] == exclude:
                continue
            for m in s["meetings"]:
                result.append(
                    {
                        "section_key": s["key"],
                        "code": s["code"],
                        "unit_department_id": s["unit"]["department_id"],
                        "day_of_week": m["day_of_week"],
                        "start_time": m["start_time"],
                        "end_time": m["end_time"],
                        "room": m["room"]["code"],
                        "linked": True,
                    }
                )
        return result

    @staticmethod
    def hours(meetings: list[dict[str, Any]]) -> float:
        distinct = {(m["day_of_week"], m["start_time"], m["end_time"]) for m in meetings}
        return round(sum(_minutes(s, e) for _d, s, e in distinct) / 60, 2)

    def allocate(self, key: str, lecturer_id: str | None) -> None:
        """Test helper: set a lecturer directly, as if done earlier."""
        self.sections[key]["lecturer"] = copy.deepcopy(self.lecturers[lecturer_id]) if lecturer_id else None

    # -- transport -----------------------------------------------------------------------

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = unquote(request.url.path)
        self.calls.append((request.method, path))
        if self.down:
            raise httpx.ConnectError("down", request=request)
        if self.bad_key or request.headers.get("X-API-Key") != API_KEY:
            return httpx.Response(403, json={"detail": "A valid X-API-Key header is required."})
        assert path.startswith(PREFIX), path
        route = path[len(PREFIX) :]
        params = dict(request.url.params)
        body = json.loads(request.content) if request.content else {}

        if route == "/authenticate/" and request.method == "POST":
            account = self.passwords.get(body.get("identifier", "").upper())
            if body.get("password") != "right-password":
                return httpx.Response(200, json={"authenticated": False})
            if account is None and body.get("identifier", "").upper() == self.lecturer_only_password:
                return httpx.Response(
                    200,
                    json={
                        "authenticated": True,
                        **self._identity(
                            "dddddddd-0000-0000-0000-000000000001", "STF/0001", "Jane Otieno", []
                        ),
                    },
                )
            if account is None:
                return httpx.Response(200, json={"authenticated": False})
            return httpx.Response(200, json={"authenticated": True, **self.identities[account]})
        if route == "/identity/":
            identity = self.identities.get(params.get("account_id", ""))
            if identity is None:
                return httpx.Response(404, json={"detail": "No active account with this id."})
            return httpx.Response(200, json=identity)
        if route == "/terms/":
            return httpx.Response(200, json={"terms": [TERM]})
        if route == "/departments/":
            return httpx.Response(200, json={"departments": self.departments})
        if route == "/sections/":
            dept = int(params["department"])
            sections = [
                copy.deepcopy(s) for s in self.sections.values() if s["unit"]["department_id"] == dept
            ]
            return httpx.Response(200, json={"term": TERM, "department_id": dept, "sections": sections})
        if route.startswith("/sections/") and route.endswith("/lecturer/") and request.method == "PATCH":
            return self._patch(route.split("/")[2], body)
        if route.startswith("/sections/"):
            key = route.split("/")[2]
            if key not in self.sections:
                return httpx.Response(404, json={"detail": "No such section in this term."})
            return httpx.Response(200, json={"term": TERM, "section": copy.deepcopy(self.sections[key])})
        if route == "/lecturers/":
            dept = params.get("department")
            rows = [
                copy.deepcopy(lec)
                for lec in self.lecturers.values()
                if dept is None or lec["department"]["id"] == int(dept)
            ]
            if params.get("term"):
                for lec in rows:
                    lec["meetings"] = self.meetings_of(lec["id"])
                    lec["weekly_hours"] = self.hours(lec["meetings"])
            return httpx.Response(200, json={"term": TERM if params.get("term") else None, "lecturers": rows})
        if route.startswith("/lecturers/") and route.endswith("/sessions/"):
            lid = route.split("/")[2]
            if lid not in self.lecturers:
                return httpx.Response(404, json={"detail": "No such lecturer."})
            meetings = self.meetings_of(lid)
            return httpx.Response(
                200,
                json={
                    "term": TERM,
                    "lecturer": copy.deepcopy(self.lecturers[lid]),
                    "weekly_hours": self.hours(meetings),
                    "meetings": meetings,
                },
            )
        return httpx.Response(404, json={"detail": f"No route {route}"})

    def _patch(self, key: str, body: dict[str, Any]) -> httpx.Response:
        section = self.sections.get(key)
        if section is None:
            return httpx.Response(404, json={"code": "not_found", "detail": "No such section in this term."})
        current = (section["lecturer"] or {}).get("id")
        if "expected_lecturer_id" in body and body["expected_lecturer_id"] != current:
            return httpx.Response(
                409,
                json={
                    "code": "stale",
                    "detail": "This class's lecturer was changed by someone else. Reload and try again.",
                    "current_lecturer_ids": [current] if current else [],
                },
            )
        lid = body.get("lecturer_id")
        if lid is not None:
            if lid not in self.lecturers:
                return httpx.Response(400, json={"code": "unknown_lecturer", "detail": "No active lecturer."})
            busy = self.meetings_of(lid, exclude=key)
            clashes = [
                {"clashes_with": o["code"]} for m in section["meetings"] for o in busy if _overlap(m, o)
            ]
            if clashes:
                return httpx.Response(
                    409,
                    json={"code": "lecturer_clash", "detail": "Already teaches then.", "clashes": clashes},
                )
            total = self.hours(busy + section["meetings"])
            if total > self.lecturers[lid]["max_weekly_teaching_hours"]:
                return httpx.Response(
                    409, json={"code": "max_hours", "detail": "Too many hours.", "weekly_hours": total}
                )
        changed = current != lid
        self.allocate(key, lid)
        return httpx.Response(
            200,
            json={
                "term": TERM,
                "section": copy.deepcopy(section),
                "changed": changed,
                "previous_lecturer_ids": [current] if current else [],
            },
        )
