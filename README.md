# Timetable Allocator

Tharaka University's teaching entry system. Each department's Chair of
Department (COD) and allocation staff enter what the department teaches in a
term, with a lecturer for every class, and publish it to the Directorate of
Examinations and Timetabling, whose **Timetable Generator** then gives every
class its day, time and room. It replaces the Word allocation form.

## A department's teaching (start here)

Terms come from the Timetable Generator (the Director opens them there), read
with `GENERATOR_API_KEY`. Each department opens its page and enters:

- **Courses**: programme, year, semester, optional sub-class and number of
  students (`BSC.COMP SCI Y1S1, 120 students`). Each becomes a class row on
  the timetable. A cohort is entered once, by its department.
- **Units**: code, title, hours per week, class length, room type (lecture
  hall, lab, seminar room) and the courses that take it. **Servicing**: a unit
  taught to another department's students is entered by the department that
  owns the unit, which picks their course from the shared list (every
  department reads every course; only its department changes it). A unit code
  is entered once per term, so nothing is timetabled twice.
- **Groups**: a unit is one whole class until the department splits it into
  groups A, B, C…; each group has its courses, the students of a course split
  between groups, its **lecturer** and the form's L, P and CF hours.
- **Lecturers**: the department's own list (title, name, staff number, FT/PT,
  phone, email, weekly hour limit). The staff number is how the same person is
  known on another department's list, by the Generator's solver and by SMARTTT,
  so a lecturer given a group needs one.
- **Paste from Excel** on every tab, with the workbook's tabs: Courses,
  Units, Groups and lecturers, Lecturers (templates downloadable on each).
- **Before publishing**: every unit has a group and every group a lecturer
  with a staff number; a course split between groups adds up to its students;
  no lecturer goes over their weekly hours, counted across every department.
  There is no clash check here: times don't exist until the Generator solves.
- **Publish** (COD only): sends the list to the Director and locks it until
  the COD **reopens** it. A unit changed after publishing is marked "changed
  since published" until it is published again.
- **Times**: once the Director publishes the timetable, each group's day,
  time and room shows on the page and on the downloads.
- **Download**: PDF, Word or Excel in the allocation form layout: one table
  per class row with a TOTAL row, "Servicing for other departments", the day,
  time and room once published, and "Prepared by". Phone numbers appear only
  on this, the department's own download.
- **All departments**: the Directorate sees every department, read-only, and
  which have published.

Lecturers reach SMARTTT through the Generator's publish (by staff number);
the Allocator no longer sends anything to SMARTTT.

API: `GET /api/generator/terms`, `GET /api/teaching/progress`,
`GET /api/teaching/{dept}`, `/api/teaching/{dept}/courses[/bulk|/{id}]`,
`/api/teaching/{dept}/units[/bulk|/{id}]`, `PUT /api/teaching/{dept}/units/{id}/groups`,
`PATCH /api/teaching/{dept}/groups/{id}`, `POST /api/teaching/{dept}/groups/bulk`,
`POST /api/teaching/{dept}/publish|reopen`, `GET /api/teaching/{dept}/export.pdf|docx|xlsx`,
`/api/teaching/{dept}/lecturers[/bulk|/{id}]`. `{dept}` is the department's
code (e.g. `CS`); a signed-in person belongs to it when SMARTTT lists them
under a department with that code.

For the Generator: `GET /api/integrations/generator/terms/{term}/submissions`
(`X-API-Key` = `GENERATOR_INBOUND_KEY`; refused when unset) returns each
published department's courses, units and groups (members, students,
lecturer by staff number and name, publish time) and the departments that
haven't published, with what changed in those that reopened.

## Needs from SMARTTT

Not built in these two repos; SMARTTT needs these for the department-first flow:

- **Accept lecturers on publish**: `generator/publish/` takes
  `lecturer_staff_number` (and `lecturer_name`) per session, and refuses the
  publish naming the staff numbers it doesn't know.
- **Add lecturers it doesn't know**: a way to create them (staff number, name,
  department, FT/PT), so a department's new lecturer can be published.
- **Match by code**: units, rooms and programmes are now typed in by
  departments and the Director, so SMARTTT matches them by code (`unit_code`,
  `room_code`, programme code and year/semester), not by SMARTTT ids.

## The earlier SMARTTT board

The pages below (`/departments/{id}`) work over SMARTTT's
`/api/v1/integrations/allocator/` endpoints with SMARTTT's `X-API-Key`, where
SMARTTT holds the published timetable and re-checks clashes under a lock.
They need those SMARTTT endpoints to be live. See `SYSTEM_HANDOFF.md` for the
whole platform.

## What it does

- **Classes**: the department's published classes (unit + group, e.g.
  `COSC 103 GR A`) with their class rows, times, rooms and current lecturer.
- **Allocate**: pick from the lecturers who are free at that hour. Busy
  lecturers are listed with the reason (teaching another class then, marked
  unavailable, or past `max_weekly_teaching_hours`). L/P/CF hours from the
  allocation form can be recorded.
- **Lecturers**: each lecturer's load this term and their unavailability.
- **Submit**: the COD submits once every class has a lecturer. Changing an
  allocation afterwards reopens it until the COD submits again.
- **Export**: the allocation form as a PDF (Course code, Course title, L, P,
  CF, Lecturer), with servicing classes in their own section.
- **All departments**: the Directorate sees every department's progress.

### Rules

| Rule | Checked by |
|---|---|
| H11 a lecturer teaches at most one class at a time | Allocator (fast feedback), then SMARTTT under a row lock (decides) |
| H12 not while marked unavailable | Allocator (SMARTTT does not know availability) |
| H12 not past `max_weekly_teaching_hours` | Allocator, then SMARTTT under the lock |
| Two people editing one class | The save sends the lecturer the screen showed; SMARTTT refuses a stale save (`STALE`) |

### Who can do what

Roles come from SMARTTT at sign-in and are re-read every
`IDENTITY_REFRESH_SECONDS`:

| SMARTTT | In the Allocator |
|---|---|
| `Department.head_of_department` | COD: allocate and submit for that department |
| `DepartmentAdmin` (admin or editor) | Department staff: allocate, not submit |
| Member of the `timetabling_office` group | Directorate: read every department and the progress overview |

## Layout

```
backend/    FastAPI + SQLAlchemy 2 + Alembic (PostgreSQL), pytest, ruff, mypy --strict
  app/api/          HTTP routes and request schemas
  app/clients/      SMARTTT client (cache <= 60 s, typed errors)
  app/services/     allocation, availability, PDF export
  app/auth.py       sign-in with SMARTTT accounts; server-side sessions, CSRF
  alembic/          migrations
  tests/            pytest, against an in-memory SMARTTT (tests/fake_smarttt.py)
frontend/   React 19 + Vite + TanStack Query + Tailwind v4 (same conventions as ATTENDANCE_fronted)
```

## Running locally

Backend (Python 3.12):

```bash
cd backend
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp ../.env.example .env                           # set DATABASE_URL, SMARTTT_*, GENERATOR_BASE_URL, GENERATOR_API_KEY, GENERATOR_INBOUND_KEY,
                                                  # ENVIRONMENT=development, COOKIE_SECURE=false
alembic upgrade head
uvicorn app.main:app --port 8001 --reload
```

Frontend (Node 20.19+): `cd frontend && npm install && npm run dev`. Vite
proxies `/api` to `http://localhost:8001` (override with `API_PROXY_TARGET`).

Everything in containers: `cp .env.example .env`, fill it in, `docker compose up --build`,
then open http://localhost:8080.

## Deploying with Docker

On a Linux server with Docker and the Compose plugin:

```bash
cp .env.example .env     # fill in POSTGRES_PASSWORD, SMARTTT_*, GENERATOR_BASE_URL,
                         # GENERATOR_API_KEY, GENERATOR_INBOUND_KEY
docker compose up -d --build
```

This runs PostgreSQL, the API (migrations run as it starts) and the web app on
port 8080, all restarting on their own. Then:

- Put an HTTPS proxy (Caddy, nginx, Traefik, or the host's) in front of port 8080;
  sign-in cookies are `Secure` and need HTTPS. Add `Strict-Transport-Security` there.
- `GENERATOR_BASE_URL` is the Generator's web address as this server reaches it
  (e.g. `https://generator.tharaka.ac.ke`), never `localhost`: inside a container
  that is the container itself.
- Back up the `db-data` volume (or `pg_dump`) on a schedule.
- Update: `git pull && docker compose up -d --build`.

## Checks

```bash
cd backend && ruff check . && ruff format --check . && mypy app && pytest
# against PostgreSQL: TEST_DATABASE_URL=postgresql+psycopg://... pytest
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
```

## Dependencies

The image installs `backend/requirements.lock`: every package pinned to the tested
version and checked by hash. After changing `backend/pyproject.toml`, regenerate it
(Linux, Python 3.12, as in the image) and run the checks again:

```bash
cd backend && uv pip compile pyproject.toml --python-version 3.12 \n  --python-platform x86_64-unknown-linux-gnu --generate-hashes --no-header -o requirements.lock
```

## Configuration

See `.env.example`. In production (`ENVIRONMENT=production`) the API refuses
to start without `SMARTTT_API_KEY` or with `COOKIE_SECURE=false`.

## Security notes

- Sessions are opaque random tokens in an httpOnly, SameSite=Lax cookie; only
  their SHA-256 is stored. Idle and absolute expiry; sign-out revokes.
- Every state-changing request needs the CSRF token (`ta_xsrf` cookie
  echoed as `X-XSRF-TOKEN`).
- Failed sign-ins are rate limited per identifier and per client address.
- The PDF export never prints phone numbers.
