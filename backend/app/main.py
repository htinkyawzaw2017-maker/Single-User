"""FastAPI application entrypoint.

  * serves the API under /api/*
  * serves the built React frontend from FRONTEND_DIST (SPA fallback)
  * optional single-user access key protection (SINGLE_USER_ACCESS_KEY)
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from . import states
from .config import settings
from .db import init_db
from .routes import exports, jobs, media, projects, segments, system, uploads

app = FastAPI(
    title="Single-User Burmese/English Movie Dubbing Tool",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Range", "Accept-Ranges"],
)

app.include_router(system.router)
app.include_router(projects.router)
app.include_router(segments.router)
app.include_router(jobs.router)
app.include_router(uploads.router)
app.include_router(media.router)
app.include_router(exports.router)


# ------------------------------------------------------------ single-user auth
AUTH_EXEMPT = {"/api/health", "/api/config"}


@app.middleware("http")
async def access_key_guard(request: Request, call_next):
    path = request.url.path
    if (
        settings.access_key
        and path.startswith("/api")
        and path not in AUTH_EXEMPT
        and path != "/api/docs"
        and not path.startswith("/api/openapi")
    ):
        supplied = (
            request.headers.get("X-Access-Key")
            or request.query_params.get("key")
        )
        if supplied != settings.access_key:
            return JSONResponse({"detail": "invalid or missing access key"},
                                status_code=401)
    return await call_next(request)


# -------------------------------------------------------------------- static
FRONTEND = Path(settings.frontend_dist)


@app.exception_handler(404)
async def spa_fallback(request: Request, exc):
    if request.method == "GET" and not request.url.path.startswith("/api"):
        index = FRONTEND / "index.html"
        if index.exists():
            return FileResponse(index)
    return JSONResponse({"detail": str(exc)}, status_code=404)


if FRONTEND.exists():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="app")


# -------------------------------------------------------------------- startup
@app.on_event("startup")
def on_startup() -> None:
    settings.load_secrets()
    init_db()
    print("=" * 60)
    print(" Single-User Burmese/English Movie Dubbing Tool")
    print(f" env={settings.app_env}  storage={'s3' if settings.storage_is_s3 else 'local'}")
    print(f" auth={'ON' if settings.access_key else 'off (set SINGLE_USER_ACCESS_KEY to enable)'}")
    print(f" providers: {settings.summary()}")
    print("=" * 60)
