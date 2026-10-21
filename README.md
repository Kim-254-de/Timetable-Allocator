# Timetable Allocator

Tharaka University's lecturer allocation system. After the Directorate of
Examinations and Timetabling publishes the teaching timetable, each
department's Chair of Department (COD) and allocation staff assign a lecturer
to every class their department owns, including classes taught to other
departments' students ("servicing"). It replaces the Word allocation form.

## The allocation form (start here)

Each department signs in and opens **Course allocation**. The units and groups
come from the **Timetable Generator** (where the Director's office enters
them), read from its `/api/integrations/allocator/` endpoints with
`GENERATOR_API_KEY`. For every unit, or every group of a split unit, the
department picks a lecturer and fills in L, P and CF, as on the Word form:

- **Lecturers**: each department keeps its own list (title, name, staff
  number, FT/PT, phone, email, weekly hour limit). The staff number is what
  recognises the same person on another department's list (and in SMARTTT).
  Lecturers can be added one at a time, inline while allocating, or pasted
  from Excel.
- **Units**: the department's units from the Generator, with their class rows
  and, once the Director has published the timetable, their times and rooms.
  Classes taught to another department's students are marked *servicing*. A
  unit the timetable doesn't have yet can still be typed in; it is flagged.
- **Checks**: once the timetable is published, a lecturer is refused for a
  class at the same time as another of their classes, or over their weekly
  hour limit.
- **Paste from Excel / Word**: rows of Course code, Group, Course title, L, P,
  CF, Lecturer ("Dr. Jane Otieno (PT)"); new lecturers are added to the list.
- **Submit**: the COD submits, which locks the form until the COD reopens it.
- **Download**: PDF, Word or Excel in the allocation form layout: one table
  per class row with a TOTAL row, "Servicing for other departments", and
  "Prepared by". Phone numbers appear only on this, the department's own download.
- **All departments**: the Directorate sees every department's progress.
- **Publish**: the COD's **Submit & publish** sends the allocation to SMARTTT
  (lecturers matched by staff number, which is required), so it reaches each
  lecturer's timetable in the app and Smart Attendance. Saving only changes the
  form here; SMARTTT gets changes when the form is submitted again. It needs
  the Director's approved timetable in SMARTTT first. SMARTTT re-checks clashes
  across every department: a class it refuses, or can't be reached for, shows
  "Not in SMARTTT" and why, and **Publish again** retries. Classes never
  allocated here are left as SMARTTT has them. SMARTTT's own timetable upload
  and allocation pages are the fallback for when the Generator or the
  Allocator can't be used.

API: `GET /api/generator/terms`, `GET /api/form/progress`,
`GET /api/form/{dept}`, `PUT /api/form/{dept}/entries`,
`POST /api/form/{dept}/entries/bulk`, `DELETE /api/form/{dept}/entries/{id}`,
`POST /api/form/{dept}/submit|reopen|publish-again`, `GET /api/form/{dept}/export.pdf|docx|xlsx`,
`/api/form/{dept}/lecturers[/bulk|/{id}]`. `{dept}` is the department's code
in the Generator (e.g. `DCOMP`); a signed-in person belongs to it when SMARTTT
lists them under a department with the same SMARTTT id, code or name.

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
cp ../.env.example .env                           # set DATABASE_URL, SMARTTT_*, GENERATOR_BASE_URL, GENERATOR_API_KEY,
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
                         # GENERATOR_API_KEY
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
