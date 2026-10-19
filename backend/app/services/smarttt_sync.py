"""
Sending the allocation form's lecturers to SMARTTT, which shows every lecturer
and student their timetable in the app and passes each class on to Smart
Attendance.

A class can be sent once SMARTTT has the Director's latest version (every class
in it then has a SMARTTT key) and its lecturer has a staff number SMARTTT knows.
SMARTTT re-checks clashes across all departments under a lock and has the last
word: a change it refuses on save is not kept here either. When SMARTTT can't
be reached, the change is kept here and waits to be sent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.clients.smarttt import (
    SmartttClient,
    SmartttError,
    SmartttNotFound,
    SmartttRefused,
)
from app.errors import ApiError
from app.models import FormEntry, Lecturer, utcnow

logger = logging.getLogger(__name__)

SENT = "sent"  # SMARTTT has this class's lecturer as on the form
PENDING = "pending"  # can be sent and hasn't been (or SMARTTT was down)
WAITING = "waiting"  # can't be sent until something changes elsewhere (e.g. the Director's version)
FAILED = "failed"  # SMARTTT refused it, or the lecturer can't be matched


@dataclass(frozen=True)
class Target:
    """Where a class's lecturer goes in SMARTTT, or why it can't go yet."""

    term_id: str | None
    key: str | None
    reason: str | None


def target(term: dict[str, Any], in_smarttt: bool, section: dict[str, Any] | None) -> Target:
    if not term.get("smarttt_term_id"):
        return Target(None, None, "This term is only in the Timetable Generator, not in SMARTTT.")
    smarttt_term = str(term["smarttt_term_id"])
    if section is None:
        return Target(smarttt_term, None, "This unit isn't in the timetable, so SMARTTT doesn't have it.")
    if not in_smarttt:
        return Target(smarttt_term, None, "Waiting for the Director's approved timetable to reach SMARTTT.")
    if not section.get("smarttt_key"):
        return Target(smarttt_term, None, "SMARTTT doesn't have this unit.")
    return Target(smarttt_term, str(section["smarttt_key"]), None)


def _local(entry: FormEntry) -> str:
    return str(entry.lecturer_id) if entry.lecturer_id else ""


def _staff_number(lecturer: Lecturer) -> str | None:
    return (lecturer.staff_number or "").strip().upper() or None


def in_sync(entry: FormEntry, where: Target) -> bool:
    return (
        entry.smarttt_synced_at is not None
        and entry.smarttt_key == where.key
        and (entry.smarttt_sent_for or "") == _local(entry)
    )


def status(entry: FormEntry | None, where: Target) -> dict[str, Any]:
    """What the form shows for a class's place in SMARTTT, without asking SMARTTT."""
    if entry is None or (entry.lecturer_id is None and not entry.smarttt_lecturer_id):
        return {"state": None, "message": None}
    if where.key is None:
        return {"state": WAITING, "message": where.reason}
    if in_sync(entry, where):
        return {"state": SENT, "message": None}
    if entry.lecturer is not None and _staff_number(entry.lecturer) is None:
        return {
            "state": FAILED,
            "message": f"Add {entry.lecturer.full_name}'s staff number to send them to SMARTTT.",
        }
    if entry.smarttt_error:
        return {"state": FAILED, "message": entry.smarttt_error}
    return {"state": PENDING, "message": "Not sent to SMARTTT yet."}


def _smarttt_lecturer_id(smarttt: SmartttClient, lecturer: Lecturer) -> str:
    staff = _staff_number(lecturer)
    if staff is None:
        raise ApiError(
            422,
            "NO_STAFF_NUMBER",
            f"Add {lecturer.full_name}'s staff number so SMARTTT can tell who they are.",
        )
    for found in smarttt.lecturers(None, None):
        if (found.get("staff_number") or "").strip().upper() == staff:
            return str(found["id"])
    raise ApiError(
        422,
        "UNKNOWN_IN_SMARTTT",
        f"SMARTTT has no active lecturer with staff number {staff}. "
        f"Check {lecturer.full_name}'s staff number.",
    )


def push(smarttt: SmartttClient, entry: FormEntry, where: Target, *, strict: bool) -> None:
    """
    Sends the entry's lecturer (or its removal) to SMARTTT unless SMARTTT
    already has it. `strict` (saving one class): a refusal raises, so the change
    isn't kept; otherwise (sending later, pasting) the reason is kept on the
    entry. SMARTTT being down never raises: the entry waits to be sent.
    """
    if where.key is None or where.term_id is None or in_sync(entry, where):
        return
    try:
        wanted = _smarttt_lecturer_id(smarttt, entry.lecturer) if entry.lecturer is not None else None
        # Once this form has set the class in SMARTTT, a change made there since
        # (on the earlier board) is refused as stale rather than overwritten.
        known = entry.smarttt_key == where.key and entry.smarttt_synced_at is not None
        smarttt.set_lecturer(
            where.key,
            where.term_id,
            wanted,
            entry.smarttt_lecturer_id if known else None,
            check_expected=known,
        )
    except ApiError as unmatched:
        if strict:
            raise
        entry.smarttt_error = unmatched.message
        return
    except SmartttNotFound:
        entry.smarttt_error = (
            "SMARTTT's timetable doesn't have this class yet. The Director needs to send the latest version."
        )
        return
    except SmartttRefused as refused:
        if strict:
            raise ApiError(409, "SMARTTT_REFUSED", refused.message, {"code": refused.code}) from refused
        entry.smarttt_error = refused.message
        return
    except SmartttError as down:
        logger.warning("Could not send %s to SMARTTT: %s", entry.key, down)
        entry.smarttt_error = f"{down.message} Use “Send to SMARTTT” to try again."
        return
    entry.smarttt_key = where.key
    entry.smarttt_lecturer_id = wanted
    entry.smarttt_sent_for = _local(entry)
    entry.smarttt_synced_at = utcnow()
    entry.smarttt_error = None


def clear(smarttt: SmartttClient, entry: FormEntry, smarttt_term_id: str | None) -> None:
    """Before a row is removed: takes the lecturer this form set back off the class in SMARTTT."""
    if not (entry.smarttt_key and entry.smarttt_synced_at and entry.smarttt_lecturer_id and smarttt_term_id):
        return
    try:
        smarttt.set_lecturer(
            entry.smarttt_key, smarttt_term_id, None, entry.smarttt_lecturer_id, check_expected=True
        )
    except (SmartttNotFound, SmartttRefused):
        return  # gone from SMARTTT, or changed there since: nothing of this form's left to clear
    except SmartttError as down:
        raise ApiError(
            503, "SMARTTT_UNAVAILABLE", f"{down.message} The lecturer has to come off the class there first."
        ) from down
