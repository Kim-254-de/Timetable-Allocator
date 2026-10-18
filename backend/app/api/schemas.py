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
