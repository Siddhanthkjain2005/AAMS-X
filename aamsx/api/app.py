"""FastAPI application factory.

The app is deliberately boring: routers, CORS, a global error handler that turns
unexpected exceptions into a message the UI can display, and a startup check that
reports cache health instead of failing to boot.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from aamsx.api.routes import datasets, experiments, reports, scenarios, system
from aamsx.config import get_settings
from aamsx.datasets.store import list_recordings
from aamsx.experiments.engine import get_engine
from aamsx.logging import configure_logging, get_logger
from aamsx.version import CODE_VERSION

log = get_logger(__name__)

DESCRIPTION = """
**AAMS-X** — Adaptive Associative Active-Sensing & Memory Scheduler.

An adaptive active-sensing research platform that decides where to observe next
under partial observability, changing activity patterns and a finite sensing
budget. Every environment is a replay of **real public e-CALLISTO spectrum
measurements**; nothing in this API is synthetic.

Occupancy labels are *derived from measurement* by a documented threshold and are
reference labels, not absolute ground truth. Panels are tagged `measured`,
`derived-label` or `model-inferred` so the distinction survives into the UI.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()
    get_engine().bind_loop(asyncio.get_running_loop())
    recordings = list_recordings(settings=settings)
    log.info(
        "api.startup",
        extra={
            "version": CODE_VERSION,
            "recordings": len(recordings),
            "cache": str(settings.cache_dir),
        },
    )
    if not recordings:
        log.warning(
            "api.cache_empty",
            extra={"hint": "run scripts/fetch_real_data.py to download real recordings"},
        )
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="AAMS-X",
        version=CODE_VERSION,
        description=DESCRIPTION,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[*settings.cors_origins, "http://localhost:4173"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for router in (
        system.router,
        datasets.router,
        scenarios.router,
        experiments.router,
        reports.router,
    ):
        app.include_router(router, prefix="/api")

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.warning("api.unhandled", extra={"path": request.url.path, "error": str(exc)})
        return JSONResponse(
            status_code=500,
            content={
                "detail": f"{type(exc).__name__}: {exc}",
                "hint": "This is a bug in AAMS-X, not in your request. "
                "The server log carries the traceback.",
            },
        )

    @app.get("/api/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok", "version": CODE_VERSION}

    return app


app = create_app()
