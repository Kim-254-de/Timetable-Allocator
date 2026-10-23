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
        return httpx.Response(404, json={"success": False})
