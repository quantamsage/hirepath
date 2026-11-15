# HirePath

![CI](https://github.com/quantamsage/hirepath/actions/workflows/ci.yml/badge.svg)

Keep every job application in one place. Add the company, role, link, status and a follow-up date, see everything on a board grouped by status, and track how your search is going on a stats page. Bring in an existing spreadsheet with CSV import, or take everything out with CSV export. Each user only ever sees their own applications.

![Board](docs/screenshots/board.png)

## Features

- Create an account and log in (email and password, short-lived JWT)
- Add, edit and delete applications: company, role, job link, status, follow-up date, notes
- Board with four columns: Applied, Interview, Offer, Rejected
- Change status straight from a card
- **Stats page:** response rate, interview rate and offer rate, a funnel (Applied → Heard back → Interviewed → Offers), applications per week for the last 12 weeks, and where everything stands now. Rates use each application's **status history**, so one that reached an interview and was later rejected still counts as interviewed.
- **CSV import:** upload your existing spreadsheet. Headers are matched loosely ("Job Title", "Date Applied", "Link" all work); only company and role are required. Import is **all or nothing**: if any row is invalid, nothing is saved and every problem is listed by spreadsheet row number.
- **CSV export:** download everything as a CSV. Cells that start with `=`, `+`, `-` or `@` are prefixed with `'` so Excel and Google Sheets don't run them as formulas.
- Record the date you applied (defaults to today), so imported history lands in the right week
- Follow-ups that are due (today or overdue, and still Applied or Interview) are highlighted. The backend decides this, not the browser.
- Friendly error messages everywhere, including field-level validation errors from the API
- Works on mobile

## Screenshots

![Stats](docs/screenshots/stats.png)

| Edit dialog | Log in | Mobile |
|---|---|---|
| ![Edit dialog](docs/screenshots/edit-dialog.png) | ![Login](docs/screenshots/login.png) | ![Mobile](docs/screenshots/mobile.png) |

## Tech stack

- **Backend:** Python 3.12, FastAPI, Pydantic v2, psycopg 3 (connection pool), PyJWT, Argon2 (argon2-cffi)
- **Frontend:** Next.js 15 (App Router), TypeScript, plain CSS
- **Database:** PostgreSQL 16 (works with any PostgreSQL 13+, including Supabase)
- **Testing:** pytest against a real Postgres database; GitHub Actions CI

## Architecture

```mermaid
flowchart LR
    U[Browser] -->|HTTPS| FE[Next.js frontend]
    FE -->|HTTPS + JSON<br/>Authorization: Bearer JWT| BE[FastAPI backend]
    BE -->|SQL, parameterised<br/>as jobtracker_app role| DB[(PostgreSQL<br/>jobtracker_* tables)]
    C[docs/openapi.yaml<br/>API contract] -. contract test .-> BE
```

The frontend never touches the database. It only calls the backend, and the backend only returns JSON.

### How each architecture rule is applied

| Rule | Where it lives |
|---|---|
| Separation of layers | `frontend/src/lib/api.ts` is the only code that talks to the backend; the frontend has no DB driver or DB URL. The backend has no HTML routes. |
| API-first | `docs/openapi.yaml` was written first. `backend/tests/test_contract.py` fails if the app's routes, methods or status codes drift from it. |
| Single source of truth | All state is in Postgres. After every change the board reloads from the API instead of patching local state. `follow_up_due` is computed in `backend/app/applications_logic.py`. |
| Schema design | `db/schema.sql`: foreign key with `ON DELETE CASCADE`, `NOT NULL`, `UNIQUE` email, `CHECK` constraints on status, URL, lengths and lowercase email. Each index has a comment explaining it. |
| Validation at the boundary | `backend/app/schemas.py`: every body, path and query parameter is a Pydantic model or typed parameter (`extra="forbid"`, length limits, URL scheme check). All SQL is in `backend/app/repository.py` and uses `%s` parameters. |
| Stateless auth | `backend/app/security.py`: Argon2id password hashes, HS256 JWT with a 30-minute expiry, algorithm pinned on decode. See the token storage trade-off below. |
| Least privilege | The app connects as `jobtracker_app`: `SELECT, INSERT` on users, CRUD on applications, `SELECT, INSERT` on the status history (it can't rewrite history), nothing else. It can't create, alter, drop or truncate (tested in `test_db_privileges.py`). Every application query includes `user_id = <id from token>`. Secrets live only in environment variables. |
| Graceful errors | `backend/app/errors.py`: one format, `{"error": {"code", "message", "details?"}}`. Unexpected errors are logged with a stack trace on the server and returned as a generic 500. |
| CORS and headers | `CORS_ORIGINS` env var, `*` rejected at startup. Backend sets `nosniff`, `X-Frame-Options: DENY`, a `frame-ancestors 'none'` CSP, `Referrer-Policy`, `Cache-Control: no-store`, and HSTS in production. The frontend sets a CSP in `next.config.ts`. |

### Token storage trade-off

The access token is kept in `sessionStorage` and sent in the `Authorization` header.

- **Why:** the frontend and backend run on different origins (ports locally, domains if deployed). Cookies across sites need `SameSite=None` and CSRF protection. A header-based token avoids CSRF completely, since browsers never attach it automatically.
- **The cost:** any JavaScript running on the page can read `sessionStorage`, so an XSS bug could steal the token. This is reduced by the CSP, React's escaping, the backend rejecting non-http(s) links, and the 30-minute expiry. `sessionStorage` (not `localStorage`) also clears when the tab closes.
- **The alternative:** an `HttpOnly` cookie can't be read by JavaScript at all. It's the stronger choice if both apps share a domain (e.g. `app.example.com` and `api.example.com`), at the cost of adding CSRF protection.

## Project structure

```
hirepath/
├── backend/
│   ├── app/
│   │   ├── main.py               # app factory, middleware (headers, errors), CORS
│   │   ├── config.py             # settings from env vars, fail fast if missing
│   │   ├── db.py                 # connection pool
│   │   ├── security.py           # Argon2 hashing, JWT create/verify, auth dependency
│   │   ├── errors.py             # consistent JSON error format
│   │   ├── schemas.py            # Pydantic request/response models
│   │   ├── applications_logic.py # business rules (follow-up due, rates)
│   │   ├── csv_io.py             # CSV import parsing/validation and export
│   │   ├── repository.py         # all SQL, parameterised, scoped by user_id
│   │   └── routers/              # auth.py, applications.py
│   ├── tests/                    # unit, API, DB-privilege and contract tests
│   ├── requirements.txt, requirements-dev.txt, pytest.ini, .env.example
├── frontend/
│   ├── src/app/                  # pages: login, register, board, stats
│   ├── src/components/           # AuthForm, ApplicationCard, ApplicationDialog, CsvTools, TopBar
│   ├── src/lib/                  # api.ts (only backend client), types.ts, format.ts
│   ├── next.config.ts            # Content-Security-Policy and headers
│   └── .env.example
├── db/schema.sql                 # tables, constraints, indexes, RLS, app role
├── docs/openapi.yaml             # API contract
├── docs/screenshots/
└── .github/workflows/ci.yml      # tests + frontend build on every push
```

## Setup (Windows, PowerShell)

### 1. Database (local PostgreSQL)

```powershell
psql -U postgres -c "CREATE DATABASE jobtracker_dev"
psql -U postgres -d jobtracker_dev -f db\schema.sql
psql -U postgres -c "ALTER ROLE jobtracker_app WITH PASSWORD '<choose-a-password>'"
```

Then set `DATABASE_URL=postgresql://jobtracker_app:<that-password>@localhost:5432/jobtracker_dev` in `backend/.env`.

### 2. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env   # then fill in DATABASE_URL and JWT_SECRET
uvicorn app.main:create_app --factory --reload
```

API docs (development only): http://localhost:8000/docs

### 3. Frontend

```powershell
cd frontend
npm install
Copy-Item .env.example .env.local
npm run dev
```

Open http://localhost:3000.

### 4. Tests

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pytest -q
```

Without a test database, the unit, contract and security tests run (35) and the database tests are skipped. To run all 75, set `TEST_ADMIN_DATABASE_URL` to a **throwaway** local Postgres database whose name contains `test` (the tests drop and recreate the tables). GitHub Actions runs the full suite on every push.

## How it works

1. **Register:** the backend lowercases the email, hashes the password with Argon2id and inserts the user. A duplicate email returns 409.
2. **Log in:** the backend checks the hash and returns a JWT whose `sub` is the user id. A wrong email and a wrong password get the same message and similar timing.
3. **Every protected request:** the `get_current_user_id` dependency verifies the token and gives the route the user id. Routes never take a user id from the request body or URL.
4. **Ownership:** every application query has `WHERE ... AND user_id = %s`. Asking for someone else's application returns 404, so you can't even tell that it exists.
5. **Board:** the frontend fetches the list and groups it into columns for display. After any change it reloads from the API.
6. **Status history:** creating an application, or changing its status, also writes a row to `jobtracker_status_events` in the same transaction. Saving without changing the status writes nothing.
7. **Stats:** one query counts current statuses and, using the history, how many applications ever reached each stage. A second query uses `generate_series` to return all 12 weeks, including weeks with no applications.
8. **Import:** `csv_io.py` validates every row with the same Pydantic model as the add form, collects all problems, and only if there are none inserts everything in one transaction.

## Limitations

- No password reset, email verification or account deletion.
- No rate limiting on login or registration, so brute-force protection relies on Argon2's cost.
- No refresh tokens: after 30 minutes you log in again.
- The frontend CSP allows `'unsafe-inline'` scripts because Next.js needs it without a nonce setup.
- Stats weeks use the server's calendar (Monday-start weeks in the database's time zone).
- Ownership is enforced in the backend. RLS blocks the Data API roles, but it doesn't yet enforce per-user rows for the app role.

## Future improvements

- Rate limiting on auth endpoints
- Per-user RLS policies (`SET LOCAL app.user_id`) as defence in depth
- Drag-and-drop between columns
- Email reminders for follow-ups
- Nonce-based CSP
- Search and filtering by company or date
- Time-to-response stats (days from applying to first reply)

## License

MIT © quantamsage. See [LICENSE](LICENSE).
