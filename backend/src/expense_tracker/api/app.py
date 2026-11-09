"""FastAPI application factory."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from expense_tracker import __version__
from expense_tracker.api.deps import AppContext
from expense_tracker.api.review_routes import router as review_router
from expense_tracker.api.routes import router
from expense_tracker.api.security import DEFAULT_HOSTS, SecurityMiddleware
from expense_tracker.clock import Clock, SystemClock
from expense_tracker.config import Settings
from expense_tracker.review.actions import reconcile_manual
from expense_tracker.services.errors import ServiceError
from expense_tracker.storage import Repository, StorageError
from expense_tracker.sync import SyncEngine, SyncService

log = logging.getLogger("expense_tracker")


def _error(status: int, code: str, message: str, details: Any = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details or {}}},
    )


def create_app(
    settings: Settings | None = None,
    clock: Clock | None = None,
    static_dir: Path | None = None,
    repo: Repository | None = None,
    start_background: bool = True,
    extra_routers: list[Any] | None = None,
    on_startup: list[Any] | None = None,
) -> FastAPI:
    """Build the application.

    ``static_dir`` points at the built frontend; when present it is served at ``/`` with SPA
    fallback so client-side routes work on reload. ``repo`` lets tests inject an open
    repository; otherwise one is opened (and locked) on startup.
    """
    settings = settings or Settings.from_env()
    clock = clock or SystemClock(settings.timezone)
    logging.basicConfig(level=settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        own = repo is None
        repository = repo or Repository(settings.data_dir, settings.backups_keep).open()
        context = AppContext(settings=settings, clock=clock, repo=repository)
        from expense_tracker.services.catalog import Catalog

        Catalog(repository).seed_defaults()
        context.transactions.freeze_default_splits()  # R14.16, once per old entry
        app.state.ctx = context
        engine = SyncEngine(repository, settings, clock)
        service = SyncService(engine, settings.scan_interval_seconds, settings.enable_watcher)
        context.extras["sync"] = service
        context.extras["after_manual_change"] = lambda tx: reconcile_manual(
            repository, tx, clock.now()
        )
        tasks: list[Any] = []
        if start_background:
            tasks.append(await service.start())
        for hook in on_startup or []:
            started = hook(app, start_background)
            if started is not None:
                tasks.append(started)
        try:
            yield
        finally:
            for t in tasks:
                await t.stop()
            if own:
                repository.close()

    app = FastAPI(
        title="Expense Tracker",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.clock = clock
    extra_hosts = [h for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h]
    app.add_middleware(SecurityMiddleware, allowed_hosts=[*DEFAULT_HOSTS, *extra_hosts])

    from starlette.exceptions import HTTPException as StarletteHTTPException

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        codes = {404: "not_found", 405: "method_not_allowed"}
        return _error(exc.status_code, codes.get(exc.status_code, "http_error"), str(exc.detail))

    @app.exception_handler(ServiceError)
    async def service_error(_: Request, exc: ServiceError) -> JSONResponse:
        return _error(exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(StorageError)
    async def storage_error(_: Request, exc: StorageError) -> JSONResponse:
        return _error(422, "invalid_data", str(exc))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": list(e.get("loc", [])), "msg": e.get("msg", "")} for e in exc.errors()]
        return _error(422, "validation_error", "invalid request", {"errors": errors})

    from pydantic import ValidationError

    @app.exception_handler(ValidationError)
    async def model_error(_: Request, exc: ValidationError) -> JSONResponse:
        errors = [{"loc": list(e.get("loc", [])), "msg": e.get("msg", "")} for e in exc.errors()]
        return _error(422, "validation_error", "invalid data", {"errors": errors})

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    app.include_router(router)
    app.include_router(review_router)
    for extra in extra_routers or []:
        app.include_router(extra)

    if static_dir is not None and (static_dir / "index.html").is_file():
        _mount_frontend(app, static_dir)

    return app


def _mount_frontend(app: FastAPI, static_dir: Path) -> None:
    assets = static_dir / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")
    index = static_dir / "index.html"
    root = static_dir.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            from fastapi import HTTPException

            raise HTTPException(status_code=404)
        candidate = (static_dir / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return FileResponse(index)
