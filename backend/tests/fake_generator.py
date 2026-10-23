"""A stand-in for the Timetable Generator's /api/integrations/allocator endpoints."""

from __future__ import annotations

from typing import Any

import httpx

TERM = "term-1"


class FakeGenerator:
    def __init__(self) -> None:
        self.key = "test-generator-key"
        self.terms: list[dict[str, Any]] = [
            {
                "id": TERM,
                "name": "September - December 2026",
                "academic_year": "2026/2027",
                "semester": 1,
                "published_version": None,
            }
        ]
        # Once the Director publishes: class key -> meetings.
        self.classes: dict[str, list[dict[str, str]]] = {}
        # The exam draft the Director shared, by our paper ids.
        self.exam_draft: dict[str, Any] = {"draft": None, "papers": []}

    def share_exams(self, papers: dict[str, tuple[str, int, list[str]]]) -> None:
        """The Director shared an exam draft: paper id -> (date, session, rooms)."""
        starts = [("08:30", "10:30"), ("11:30", "13:30"), ("14:30", "16:30")]
        self.exam_draft = {
            "draft": {
                "id": "d-1",
                "name": "Exam draft 1",
                "shared_at": "2026-11-01T08:00:00+00:00",
                "status": "draft",
            },
            "papers": [
                {
                    "paper_ref": ref,
                    "codes": ref,
                    "date": day,
                    "session": session,
                    "start_time": starts[session][0],
                    "end_time": starts[session][1],
                    "rooms": rooms,
                }
                for ref, (day, session, rooms) in papers.items()
            ],
        }

    def publish(self, classes: dict[str, list[tuple[str, str, str, str]]]) -> None:
        """The Director published version 1 with these classes' meetings (day, start, end, room)."""
        self.terms[0]["published_version"] = 1
        self.classes = {
            key: [{"day_of_week": d, "start_time": s, "end_time": e, "room": r} for d, s, e, r in meetings]
            for key, meetings in classes.items()
        }

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.headers.get("X-API-Key") != self.key:
            return httpx.Response(401, json={"success": False})
        path = request.url.path.removeprefix("/api/integrations/allocator")
        if path == "/terms":
            return httpx.Response(200, json={"success": True, "data": self.terms})
        if path == f"/terms/{TERM}/times":
            data = {"published_version": self.terms[0]["published_version"], "classes": self.classes}
            return httpx.Response(200, json={"success": True, "data": data})
        if path == f"/terms/{TERM}/exam-draft":
            return httpx.Response(200, json={"success": True, "data": self.exam_draft})
        return httpx.Response(404, json={"success": False})
