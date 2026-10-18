# Timetable Allocator

Tharaka University's lecturer allocation system. After the Directorate of
Examinations and Timetabling publishes the teaching timetable, each
department's Chair of Department (COD) and allocation staff assign a lecturer
to every class their department owns, including classes taught to other
departments' students ("servicing"). It replaces the Word allocation form.

The Allocator talks **only to SMARTTT** (never to the Timetable Generator),
over SMARTTT's `/api/v1/integrations/allocator/` endpoints with its own
`X-API-Key`. SMARTTT holds the published timetable and is the truth for who
teaches what; every allocation is written there on save, and SMARTTT
re-checks clashes under a lock. See `SYSTEM_HANDOFF.md` for the whole platform.

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
cp ../.env.example .env                           # set DATABASE_URL, SMARTTT_BASE_URL, SMARTTT_API_KEY,
                                                  # ENVIRONMENT=development, COOKIE_SECURE=false
alembic upgrade head
uvicorn app.main:app --port 8001 --reload
```

Frontend (Node 20.19+): `cd frontend && npm install && npm run dev`. Vite
proxies `/api` to `http://localhost:8001` (override with `API_PROXY_TARGET`).

Everything in containers: `cp .env.example .env`, fill it in, `docker compose up --build`,
then open http://localhost:8080.

## Checks

```bash
cd backend && ruff check . && ruff format --check . && mypy app && pytest
# against PostgreSQL: TEST_DATABASE_URL=postgresql+psycopg://... pytest
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
```

## Configuration

See `.env.example`. In production (`ENVIRONMENT=production`) the API refuses
to start without `SMARTTT_API_KEY` or with `COOKIE_SECURE=false`.

## Security notes

- Sessions are opaque random tokens in an httpOnly, SameSite=Lax cookie; only
  their SHA-256 is stored. Idle and absolute expiry; sign-out revokes.
- Every state-changing request needs the CSRF token (`XSRF-TOKEN` cookie
  echoed as `X-XSRF-TOKEN`).
- Failed sign-ins are rate limited per identifier and per client address.
- The PDF export never prints phone numbers.
