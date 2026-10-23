from __future__ import annotations

import re
from datetime import date, time
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


Id = Annotated[str, StringConstraints(pattern=r"^[0-9a-fA-F-]{32,36}$")]
Programme = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
SubClass = Annotated[str, StringConstraints(strip_whitespace=True, max_length=10)]
RoomType = Literal["lecture_hall", "lab", "seminar"]
CourseMode = Literal["regular", "odel", "weekend", "evening", "school_based", "part_time"]


class CourseBody(_Strict):
    """A cohort: 'BSC.CS', year 1, semester 1, 120 students (sub-class optional)."""

    programme: Programme
    year: Annotated[int, Field(ge=1, le=7)]
    semester: Annotated[int, Field(ge=1, le=3)]
    sub_class: SubClass = ""
    students: Annotated[int, Field(ge=1, le=5000)]
    mode: CourseMode = "regular"


class CoursePatch(_Strict):
    programme: Programme | None = None
    year: Annotated[int, Field(ge=1, le=7)] | None = None
    semester: Annotated[int, Field(ge=1, le=3)] | None = None
    sub_class: SubClass | None = None
    students: Annotated[int, Field(ge=1, le=5000)] | None = None
    mode: CourseMode | None = None


class UnitBody(_Strict):
    code: UnitCode
    title: Name
    weekly_hours: Annotated[int, Field(ge=1, le=20)]
    class_length: Annotated[int, Field(ge=1, le=6)]
    room_type: RoomType = "lecture_hall"
    # The courses that take it: this department's or, for servicing, another's.
    course_ids: Annotated[list[Id], Field(min_length=1, max_length=50)]


class UnitPatch(_Strict):
    code: UnitCode | None = None
    title: Name | None = None
    weekly_hours: Annotated[int, Field(ge=1, le=20)] | None = None
    class_length: Annotated[int, Field(ge=1, le=6)] | None = None
    room_type: RoomType | None = None
    course_ids: Annotated[list[Id], Field(min_length=1, max_length=50)] | None = None


class MemberBody(_Strict):
    course_id: Id
    # Set when the course is split between groups; left out = the whole course.
    students: Annotated[int, Field(ge=1, le=5000)] | None = None


class GroupBody(_Strict):
    """One class of a unit. `label` is "" for the whole class, else "A", "GR B"..."""

    label: Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] = ""
    members: Annotated[list[MemberBody], Field(min_length=1, max_length=50)]
    lecturer_id: Id | None = None
    lecture_hours: Hours | None = None
    practical_hours: Hours | None = None
    cf_hours: Hours | None = None


class GroupsBody(_Strict):
    groups: Annotated[list[GroupBody], Field(min_length=1, max_length=26)]


class GroupPatch(_Strict):
    lecturer_id: Id | None = None
    lecture_hours: Hours | None = None
    practical_hours: Hours | None = None
    cf_hours: Hours | None = None


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
    max_exam_duties: Annotated[int, Field(ge=1, le=100)] | None = None
    active: bool = True


class LecturerPatch(_Strict):
    title: Annotated[str, StringConstraints(strip_whitespace=True, max_length=30)] | None = None
    full_name: Name | None = None
    staff_number: StaffNumber | None = None
    employment_type: Literal["full_time", "part_time"] | None = None
    phone: Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)] | None = None
    email: Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)] | None = None
    max_weekly_hours: Annotated[int, Field(ge=0, le=60)] | None = None
    max_exam_duties: Annotated[int, Field(ge=0, le=100)] | None = None
    active: bool | None = None


class BulkBody(_Strict):
    """Rows pasted from Excel or Word, one dict per row, keyed by column heading."""

    rows: Annotated[list[dict[str, str | int | float | None]], Field(min_length=1, max_length=2000)]


# -- exams ----------------------------------------------------------------------------------


class PaperBody(_Strict):
    """A written exam paper: one unit, or several sitting one shared paper ("BITE 131/COSC 130")."""

    unit_ids: Annotated[list[Id], Field(min_length=1, max_length=10)]
    title: Text = ""
    examiner_id: Id | None = None
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] = ""


class PaperPatch(_Strict):
    unit_ids: Annotated[list[Id], Field(min_length=1, max_length=10)] | None = None
    title: Text | None = None
    examiner_id: Id | None = None
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


class NoWrittenExamBody(_Strict):
    no_written_exam: bool


class PracticalBody(_Strict):
    unit_id: Id
    date: date
    start_time: time
    end_time: time


class InvigilatorBody(_Strict):
    """
    Who invigilates the paper: its main invigilator (room "") or the one in an
    extra room (its code); any department's lecturer, by id; null clears it.
    """

    room: Annotated[str, StringConstraints(strip_whitespace=True, max_length=30)] = ""
    lecturer_id: Id | None
