from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

SECTION_KEY = r"^\d+-[A-Z0-9]+$"
HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"
TeachingDay = Literal["MON", "TUE", "WED", "THU", "FRI"]
Hours = Annotated[float, Field(ge=0, le=500)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginBody(_Strict):
    identifier: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    password: Annotated[str, StringConstraints(min_length=1, max_length=1024)]


class AllocationBody(_Strict):
    """
    `expected_lecturer_id` is the lecturer the screen showed (null = none):
    the save is refused if someone changed it meanwhile.
    """

    lecturer_id: str | None
    expected_lecturer_id: str | None
    lecture_hours: Hours | None = None
    practical_hours: Hours | None = None
    cf_hours: Hours | None = None

    @field_validator("lecturer_id", "expected_lecturer_id")
    @classmethod
    def _uuid_like(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[0-9a-fA-F-]{32,36}", value):
            raise ValueError("must be a SMARTTT lecturer id")
        return value


class Period(_Strict):
    day_of_week: TeachingDay
    start_time: Annotated[str, StringConstraints(pattern=HHMM)]
    end_time: Annotated[str, StringConstraints(pattern=HHMM)]
    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)] = ""


class AvailabilityBody(_Strict):
    unavailable: Annotated[list[Period], Field(max_length=50)]


Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=255)]
UnitCode = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=64)]


class FormEntryBody(_Strict):
    """
    One row of a department's allocation form. For a unit in the Generator the
    title and class rows come from the Generator; `unit_title` and
    `class_rows` are only used for a unit the timetable doesn't have yet.
    """

    unit_code: UnitCode
    group_label: Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] = ""
    unit_title: Text = ""
    class_rows: Annotated[list[Text], Field(max_length=20)] = []
    lecturer_id: str | None = None
    lecture_hours: Hours | None = None
    practical_hours: Hours | None = None
    cf_hours: Hours | None = None

    @field_validator("lecturer_id")
    @classmethod
    def _uuid_like(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[0-9a-fA-F-]{32,36}", value):
            raise ValueError("must be a lecturer id")
        return value


StaffNumber = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


class LecturerBody(_Strict):
    title: Annotated[str, StringConstraints(strip_whitespace=True, max_length=30)] = ""
    full_name: Name
    # How SMARTTT knows the lecturer, so their classes reach their timetable and attendance.
    staff_number: StaffNumber
    employment_type: Literal["full_time", "part_time"] = "full_time"
    phone: Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)] = ""
    email: Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)] = ""
    max_weekly_hours: Annotated[int, Field(ge=1, le=60)] | None = None
    active: bool = True


class LecturerPatch(_Strict):
    title: Annotated[str, StringConstraints(strip_whitespace=True, max_length=30)] | None = None
    full_name: Name | None = None
    staff_number: StaffNumber | None = None
    employment_type: Literal["full_time", "part_time"] | None = None
    phone: Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)] | None = None
    email: Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)] | None = None
    max_weekly_hours: Annotated[int, Field(ge=0, le=60)] | None = None
    active: bool | None = None


class BulkBody(_Strict):
    """Rows pasted from Excel or Word, one dict per row, keyed by column heading."""

    rows: Annotated[list[dict[str, str | int | float | None]], Field(min_length=1, max_length=2000)]
