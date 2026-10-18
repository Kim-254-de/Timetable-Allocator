"""Week-time helpers. Days are MON..FRI; times are campus time (Africa/Nairobi) HH:MM strings."""

from __future__ import annotations

from datetime import time
from typing import Any

DAYS = ("MON", "TUE", "WED", "THU", "FRI")
DAY_ORDER = {day: index for index, day in enumerate((*DAYS, "SAT", "SUN"))}


def parse_hhmm(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


def hhmm(value: time) -> str:
    return value.strftime("%H:%M")


def minutes(start: str, end: str) -> int:
    a, b = parse_hhmm(start), parse_hhmm(end)
    return (b.hour * 60 + b.minute) - (a.hour * 60 + a.minute)


def overlaps(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Two meetings ({day_of_week, start_time, end_time}) share time; back-to-back is not overlap."""
    return bool(
        a["day_of_week"] == b["day_of_week"]
        and a["start_time"] < b["end_time"]
        and b["start_time"] < a["end_time"]
    )


def weekly_hours(meetings: list[dict[str, Any]]) -> float:
    """Each distinct (day, start, end) counted once, as SMARTTT counts it."""
    distinct = {(m["day_of_week"], m["start_time"], m["end_time"]) for m in meetings}
    return round(sum(minutes(s, e) for _d, s, e in distinct) / 60, 2)
