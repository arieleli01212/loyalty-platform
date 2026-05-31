# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Architecture

Three deployable units, developed independently:

- **`backend/`** — FastAPI + SQLModel async API. Single `app.main:app` ASGI entry. Routers are split: `app/api/v1/*` (JSON API, JWT-auth, mounted at `/api/v1`) and `app/api/public.py` (no-auth HTML pages at `/e/{slug}` enrollment + `/pass/{serial}` stub wallet pass). Tables are created at startup via `create_db_and_tables()` in the lifespan handler; Alembic is set up but the runtime path does not depend on migrations.
- **`frontend-scanner/`** — Vite + React + TS PWA for staff. Uses `html5-qrcode` to read a card's `barcode_token` and posts to `/api/v1/scan` to stamp/redeem.
- **`frontend-dashboard/`** — Vite + React + TS SPA for merchants (programs, customers, analytics; `recharts` for charts).

CORS origins are driven by `CORS_ORIGINS` in `.env` (JSON-array string parsed by pydantic-settings — must be valid JSON, e.g. `["http://localhost:5173"]`).

### Core domain flow

Identity model: `MerchantUser` → `Business` → `RewardProgram` → `LoyaltyCard` (one per Customer per program). A `LoyaltyCard` carries a `barcode_token` (random URL-safe) that the scanner reads; a `pass_serial` (UUID) addresses the hosted wallet pass page.

All stamp/redeem logic lives in `app/services/loyalty.py::process_scan` — this is the single chokepoint and the right place to change loyalty rules. It enforces, in order:

1. Card exists and belongs to the scanning staff's `business_id` (403 on mismatch — multi-tenancy is enforced here, not by Postgres RLS).
2. Card and Program are active.
3. **Idempotency** — if `idempotency_key` matches a prior `ScanEvent`, returns current card state without mutating (clients should send a UUID per scan attempt).
4. **Stamp throttling** — rejects 429 if another stamp on the same card occurred within `STAMP_THROTTLE_MINUTES` (default 2; configurable via env).
5. On stamp: increments `current_stamps`/`lifetime_stamps`; when `current_stamps >= program.stamps_required`, resets `current_stamps` to 0 and increments `rewards_available`. On redeem: decrements `rewards_available` (400 if none).
6. Writes a `ScanEvent` (analytics + idempotency record) and calls the wallet provider.

Wallet providers are pluggable behind `app/services/wallet/provider.py`; only `stub.py` is implemented (no-op update; the "pass" is the hosted HTML page at `/pass/{serial}`). `WALLET_PROVIDER` env var selects the implementation.

### Auth

JWT via `python-jose` (see `app/core/security.py` / `app/core/deps.py`). Access + refresh tokens; `ACCESS_TOKEN_EXPIRE_MINUTES` / `REFRESH_TOKEN_EXPIRE_DAYS` from env. `bcrypt` is pinned to `4.0.1` because newer versions break `passlib`'s detection — don't bump without testing.

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

# Alembic (DB schema lives under migrations/versions/; runtime uses create_all,
# so migrations are only needed when targeting Postgres in deployment)
alembic revision --autogenerate -m "msg"
alembic upgrade head
```

Tests use in-memory SQLite (`conftest.py`) and override the `get_session` dependency — they never touch the dev `loyalty.db`. Shared fixtures: `client`, `registered_user`, `auth_headers`, `program`, `loyalty_card`.

### Frontends

Both apps use the same scripts:

```bash
cd frontend-scanner    # or frontend-dashboard
npm install
npm run dev            # vite dev server (scanner :5173, dashboard typically :5174)
npm run build
npm run typecheck      # tsc --noEmit — there is no eslint
```

The scanner is a PWA (`vite-plugin-pwa`); service-worker behavior only manifests in `build` + `preview`, not `dev`.

### Full stack via Docker

```bash
docker-compose up      # backend on :8000, Postgres on :5432
```

Compose sets `DATABASE_URL` to the async Postgres URL; without compose, `.env` defaults to `sqlite+aiosqlite:///./loyalty.db`. The async driver prefix (`+asyncpg` / `+aiosqlite`) is required — plain `postgresql://` will fail at engine creation.

## Conventions worth knowing

- All DB access is async — use `await session.execute(select(...))` + `.scalar_one_or_none()` patterns (see `services/loyalty.py`). Don't import the sync SQLModel `Session`.
- Multi-tenant boundary checks (`card.business_id == current_user.business_id`) are required in every new endpoint that touches business-scoped data — there is no row-level enforcement.
- New v1 endpoints: add a module under `app/api/v1/`, then register it in `app/api/v1/router.py` (it is not auto-discovered).
- Schemas (Pydantic request/response) live in `app/schemas/`, separate from SQLModel table classes in `app/models/`.
