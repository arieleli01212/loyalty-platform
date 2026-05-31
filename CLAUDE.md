# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Architecture

Two deployable units:

- **`backend/`** — FastAPI + SQLModel async API. Single `app.main:app` ASGI entry. Routers are split: `app/api/v1/*` (JSON API, JWT-auth, mounted at `/api/v1`) and `app/api/public.py` (no-auth HTML pages at `/e/{slug}` enrollment + `/pass/{serial}` PWA wallet pass, plus its manifest/icons/service worker). Tables are created at startup via `create_db_and_tables()` in the lifespan handler; Alembic is set up but the runtime path does not depend on migrations. In production, `main.py` also serves the built React app from `./static` and falls back to `index.html` for client-side routes — same-origin deploy, no CORS to manage.
- **`frontend-dashboard/`** — Vite + React + TS SPA covering both merchant dashboard (programs, customers, analytics, staff, branding, enrollment QR) and the staff scanner at `/scanner`. Auth role is stored on `AuthContext`; `AuthGuard` redirects `staff` users to `/scanner` and blocks every other route.

`CORS_ORIGINS` (JSON-array string in env) only matters if you serve the frontend from a different origin than the backend — in the Render single-origin deploy it can be `[]`.

### Core domain flow

Identity model: `MerchantUser` (role: `owner` | `staff`) → `Business` → `RewardProgram` → `LoyaltyCard` (one per Customer per program). A `LoyaltyCard` carries a `barcode_token` (random URL-safe) that the scanner reads; a `pass_serial` (UUID) addresses the hosted PWA pass page.

All stamp/redeem logic lives in `app/services/loyalty.py::process_scan` — this is the single chokepoint and the right place to change loyalty rules. It enforces, in order:

1. Card exists and belongs to the scanning staff's `business_id` (403 on mismatch — multi-tenancy is enforced here, not by Postgres RLS).
2. Card and Program are active.
3. **Idempotency** — if `idempotency_key` matches a prior `ScanEvent`, returns current card state without mutating (clients should send a UUID per scan attempt).
4. **Stamp throttling** — rejects 429 if another stamp on the same card occurred within `STAMP_THROTTLE_MINUTES` (default 2; configurable via env).
5. On stamp: increments `current_stamps`/`lifetime_stamps`; when `current_stamps >= program.stamps_required`, resets `current_stamps` to 0 and increments `rewards_available`. On redeem: decrements `rewards_available` (400 if none).
6. Writes a `ScanEvent` (analytics + idempotency record) and calls the wallet provider.

Wallet providers are pluggable behind `app/services/wallet/provider.py`; only `stub.py` is implemented (no-op update; the "pass" is the hosted PWA HTML page at `/pass/{serial}` — installable to home screen on iOS and Android). `WALLET_PROVIDER` env var selects the implementation.

### Auth

JWT via `python-jose` (see `app/core/security.py` / `app/core/deps.py`). Access + refresh tokens; `ACCESS_TOKEN_EXPIRE_MINUTES` / `REFRESH_TOKEN_EXPIRE_DAYS` from env. `bcrypt` is pinned to `4.0.1` because newer versions break `passlib`'s detection — don't bump without testing. Staff-only and owner-only endpoints use `get_current_user` / `get_owner_user` dependencies.

### Deployment

- **Production deploy is on Render** via `render.yaml` (Blueprint). The root `Dockerfile` is a multi-stage build: stage 1 builds the React dashboard with `VITE_API_BASE=""` so the SPA uses relative URLs, stage 2 is the Python image with the built `dist/` copied to `backend/static/`. Render injects `$PORT`.
- **Database URL normalization** happens in `app/db.py::_normalize_db_url`: rewrites `postgresql://...?sslmode=require` (the form Neon/Render/Heroku hand out) to `postgresql+asyncpg://...?ssl=require`. Paste hosted URLs verbatim into `DATABASE_URL` — the app fixes them.
- **The backend `Dockerfile` and `docker-compose.yml`** are for *local* dev only (single-stage, mounts source for hot reload, runs against a local Postgres). The production image is built from the root `Dockerfile`.

## Commands

### Backend (run from `backend/`)

```bash
# Setup
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Run dev server (reads ../.env)
uvicorn app.main:app --reload --port 8000

# Tests (pytest-asyncio in auto mode — no @pytest.mark.asyncio needed)
pytest                              # all tests
pytest tests/test_scan.py           # one file
pytest tests/test_scan.py::test_stamp_increments  # one test
pytest -k "throttle"                # by keyword

# Lint (ruff is installed in venv but not in requirements.txt — dev tool only)
python -m ruff check app/
python -m ruff check app/ --fix

# Alembic (DB schema lives under migrations/versions/; runtime uses create_all,
# so migrations are only needed when targeting Postgres in deployment)
alembic revision --autogenerate -m "msg"
alembic upgrade head
```

Tests use in-memory SQLite (`conftest.py`) and override the `get_session` dependency — they never touch the dev `loyalty.db`. Shared fixtures: `client`, `registered_user`, `auth_headers`, `program`, `loyalty_card`.

### Frontend (run from `frontend-dashboard/`)

```bash
npm install
npm run dev            # vite dev server on :5173
npm run build          # output to dist/ — production build
npm run typecheck      # tsc --noEmit — there is no eslint
```

In dev the api client points at `http://localhost:8000` (override with `VITE_API_BASE`). In a prod build (`import.meta.env.DEV === false`) it falls back to relative URLs, which is what the Render single-origin deploy expects.

### Full stack via Docker (local Postgres testing)

```bash
docker-compose up      # backend on :8000, Postgres on :5432
```

Uses `backend/Dockerfile` (single-stage). The async driver prefix (`+asyncpg` / `+aiosqlite`) is required — plain `postgresql://` will be normalized at startup by `_normalize_db_url`.

## Conventions worth knowing

- All DB access is async — use `await session.execute(select(...))` + `.scalar_one_or_none()` patterns (see `services/loyalty.py`). Don't import the sync SQLModel `Session`.
- Multi-tenant boundary checks (`card.business_id == current_user.business_id`) are required in every new endpoint that touches business-scoped data — there is no row-level enforcement.
- Owner-only endpoints should depend on `get_owner_user` (raises 403 if the user's role is `staff`).
- New v1 endpoints: add a module under `app/api/v1/`, then register it in `app/api/v1/router.py` (it is not auto-discovered).
- Schemas (Pydantic request/response) live in `app/schemas/`, separate from SQLModel table classes in `app/models/`.
- **Apostrophe trap in `app/api/public.py`**: HTML/JS templates are Python triple-quoted f-strings. `\'` collapses to `'` and produces broken JS — use HTML entities (`&apos;`), double-quoted JS strings, or a non-f-string assigned separately and injected with `{}`. The service worker source in this file is intentionally a raw string (`r"""..."""`), not an f-string, for exactly this reason.
