"""
The department's allocation as a PDF, in the layout of the Word allocation
form departments send today: one table per class row ("BSC.COMP SCI - YEAR 1
SEMESTER 2") with Course code, Course title, L, P, CF and Lecturer
(FT/PT), then the classes taught for other departments under "Servicing for
other departments". Phone numbers are deliberately not printed.
"""

from __future__ import annotations

from collections import defaultdict
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

EMPLOYMENT = {"full_time": "FT", "part_time": "PT"}


def _hours(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:g}"


def _lecturer_cell(section: dict[str, Any]) -> str:
    lecturer = section.get("lecturer")
    if not lecturer:
        return "To be allocated"
    kind = EMPLOYMENT.get(lecturer.get("employment_type") or "", "")
    title = f"{lecturer['title']} " if lecturer.get("title") else ""
    return f"{title}{lecturer['full_name']}" + (f" ({kind})" if kind else "")


def _row_heading(row: dict[str, Any]) -> str:
    semester = f" SEMESTER {row['study_semester']}" if row.get("study_semester") else ""
    stream = f" ({row['stream']})" if row.get("stream") else ""
    programme = row.get("program_code") or row.get("program_name") or "Unknown programme"
    return f"{programme}{stream} - YEAR {row['year_of_study']}{semester}"


def build_pdf(department: dict[str, Any], board: dict[str, Any], prepared_by: str) -> bytes:
    styles = getSampleStyleSheet()
    cell = ParagraphStyle("cell", parent=styles["BodyText"], fontSize=8, leading=10)
    heading = ParagraphStyle("heading", parent=styles["Heading4"], spaceBefore=8, spaceAfter=4)

    own: dict[str, list[dict[str, Any]]] = defaultdict(list)
    servicing: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for section in board["sections"]:
        rows = section["class_rows"] or [{"program_code": None, "year_of_study": 0}]
        target = servicing if section.get("servicing") else own
        # A group shared by several class rows is listed under its first row,
        # with the others named, as the Word form does ("Group K: MATH/CHEM, AGRI/CHEM").
        heading_text = _row_heading(rows[0])
        target[heading_text].append(section)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=f"{department['name']} allocation",
        author=prepared_by,
    )
    term = board["term"]
    story: list[Any] = [
        Paragraph("THARAKA UNIVERSITY", styles["Title"]),
        Paragraph(f"{department['name'].upper()}", styles["Heading2"]),
        Paragraph(
            f"COURSE ALLOCATION - {term['academic_year']} SEMESTER {term['semester']}", styles["Heading3"]
        ),
        Spacer(1, 4 * mm),
    ]

    def table_for(sections: list[dict[str, Any]]) -> Table:
        data: list[list[Any]] = [["Course code", "Course title", "L", "P", "CF", "Lecturer"]]
        for s in sorted(sections, key=lambda x: x["code"]):
            allocation = s.get("allocation") or {}
            title = s["unit"]["name"]
            if len(s["class_rows"]) > 1:
                others = ", ".join(r.get("program_code") or "?" for r in s["class_rows"][1:])
                title += f" (with {others})"
            data.append(
                [
                    Paragraph(s["code"], cell),
                    Paragraph(title, cell),
                    _hours(allocation.get("lecture_hours")),
                    _hours(allocation.get("practical_hours")),
                    _hours(allocation.get("cf_hours")),
                    Paragraph(_lecturer_cell(s), cell),
                ]
            )
        table = Table(data, colWidths=[28 * mm, 62 * mm, 10 * mm, 10 * mm, 10 * mm, 60 * mm], repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
                    ("FONT", (0, 1), (-1, -1), "Helvetica", 8),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.black),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5e7eb")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (2, 1), (4, -1), "CENTER"),
                ]
            )
        )
        return table

    for title in sorted(own):
        story.append(Paragraph(title, heading))
        story.append(table_for(own[title]))
    if servicing:
        story.append(Paragraph("SERVICING FOR OTHER DEPARTMENTS", styles["Heading3"]))
        for title in sorted(servicing):
            story.append(Paragraph(title, heading))
            story.append(table_for(servicing[title]))
    if not board["sections"]:
        story.append(Paragraph("No published classes for this department this term.", styles["BodyText"]))

    submission = board.get("submission")
    story.append(Spacer(1, 8 * mm))
    if submission and submission["is_current"]:
        story.append(
            Paragraph(
                f"Submitted by {submission['submitted_by']} on {submission['submitted_at'][:10]}.",
                styles["BodyText"],
            )
        )
    else:
        story.append(Paragraph("Not yet submitted by the Chair of Department.", styles["BodyText"]))
    story.append(Paragraph(f"Printed by {prepared_by}.", styles["BodyText"]))
    doc.build(story)
    return buffer.getvalue()
