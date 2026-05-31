from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.db import create_db_and_tables
from app.api.v1.router import router as v1_router
from app.api.public import router as public_router
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_db_and_tables()
    yield


app = FastAPI(
    title="Digital Loyalty Card Platform",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router, prefix="/api/v1")
app.include_router(public_router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Serve the built React dashboard (in production)
# ---------------------------------------------------------------------------
# The Dockerfile builds frontend-dashboard and copies the output to ./static
# inside the container. In local dev (running uvicorn from backend/) this
# directory simply won't exist, so the SPA mount is skipped and the React app
# is served by `npm run dev` as usual.

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

if STATIC_DIR.is_dir():
    # Vite emits its hashed JS/CSS into /assets — long-lived, cache-friendly.
    assets_dir = STATIC_DIR / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    # SPA fallback. Must be registered LAST so it doesn't shadow the API
    # routers above. Serves a static file if one exists at the requested path
    # (e.g. /favicon.ico, /vite.svg); otherwise returns index.html so the
    # React router can take over.
    _STATIC_ROOT = STATIC_DIR.resolve()
    _INDEX = STATIC_DIR / "index.html"

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        if full_path:
            candidate = (STATIC_DIR / full_path).resolve()
            try:
                candidate.relative_to(_STATIC_ROOT)
            except ValueError:
                # Path traversal attempt — refuse.
                raise HTTPException(status_code=404)
            if candidate.is_file():
                return FileResponse(candidate)

        if _INDEX.is_file():
            return FileResponse(_INDEX)
        raise HTTPException(status_code=404)
