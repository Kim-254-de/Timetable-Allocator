"""A stand-in for the Timetable Generator's /api/integrations/allocator endpoints."""

from __future__ import annotations

from typing import Any

import httpx

TERM = "term-1"
CS_DEPT = {"id": 100001, "code": "CS", "name": "Computer Science", "smarttt_id": None}
ED_DEPT = {"id": 100002, "code": "ED", "name": "Education", "smarttt_id": None}


def _section(
    unit: str,
    group: str,
    name: str,
    department: dict[str, Any],
    rows: list[tuple[str, int, dict[str, Any]]],
    meetings: list[tuple[str, str, str, str]],
) -> dict[str, Any]:
    key = f"{unit.replace(' ', '')}-{group.replace(' ', '') or 'MAIN'}"
    return {
        "key": key,
        "unit_code": unit,
        "unit_name": name,
        "group": group,
        "department": department,
        "students": sum(r[1] for r in rows),
        "weekly_hours": 3,
        "class_rows": [
            {
                "label": label,
                "program_code": label,
                "study_year": 1,
                "study_semester": 1,
                "students": n,
                "department": {"code": d["code"], "name": d["name"]},
            }
            for label, n, d in rows
        ],
        "meetings": [
            {"day_of_week": d, "start_time": s, "end_time": e, "room": r} for d, s, e, r in meetings
        ],
    }


class FakeGenerator:
    def __init__(self) -> None:
        self.key = "test-generator-key"
        self.terms = [
            {"id": TERM, "name": "September - December 2026", "academic_year": "2026/2027", "semester": 1}
        ]
        self.published_version: int | None = 1
        self.sections = [
            _section(
                "COSC 103",
                "GR A",
                "Intro to Programming",
                CS_DEPT,
                [("BSC.CS Y1S1", 60, CS_DEPT)],
                [("TUE", "10:00", "12:00", "STB 1")],
            ),
            _section(
                "COSC 103",
                "GR B",
                "Intro to Programming",
                CS_DEPT,
                [("BED.SCI Y1S1", 50, ED_DEPT)],
                [("TUE", "11:00", "13:00", "STB 2")],
            ),
            _section(
                "COSC 200",
                "",
                "Data Structures",
                CS_DEPT,
                [("BSC.CS Y2S1", 40, CS_DEPT)],
                [("WED", "08:00", "11:00", "UTC 1")],
            ),
            _section(
                "EDFO 111",
                "",
                "Foundations of Education",
                ED_DEPT,
                [("BED.SCI Y1S1", 80, ED_DEPT)],
                [("MON", "08:00", "10:00", "ED 1")],
            ),
        ]

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.headers.get("X-API-Key") != self.key:
            return httpx.Response(401, json={"success": False})
        path = request.url.path.removeprefix("/api/integrations/allocator")
        if path == "/terms":
            return httpx.Response(200, json={"success": True, "data": self.terms})
        if path == f"/terms/{TERM}/sections":
            data = {
                "term": self.terms[0],
                "published_version": self.published_version,
                "sections": self.sections,
            }
            return httpx.Response(200, json={"success": True, "data": data})
        return httpx.Response(404, json={"success": False})
