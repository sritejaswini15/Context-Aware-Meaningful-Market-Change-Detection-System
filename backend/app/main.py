"""Knoww API - know what matters."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging, log_event, request_id_var


def _startup() -> None:
    from app.core.db import session_scope
    from app.services.market_data.ingestion import bootstrap_reference_data

    try:
        with session_scope() as db:
            bootstrap_reference_data(db)
    except Exception as exc:  # the API must still boot so health checks can report the problem
        log_event("startup.bootstrap_failed", logging.ERROR, error=str(exc))
    s = get_settings()
    if s.queue_backend == "inline":
        from app.workers.scheduler import start_local_scheduler

        start_local_scheduler(mode="api-inline")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if get_settings().app_env != "test":
        _startup()
    yield


def create_app() -> FastAPI:
    s = get_settings()
    configure_logging(s.log_level, s.log_json)
    if s.sentry_dsn:
        import sentry_sdk

        sentry_sdk.init(dsn=s.sentry_dsn, environment=s.app_env, release=s.app_version, traces_sample_rate=0.05, send_default_pii=False)

    app = FastAPI(
        title="Knoww API",
        version=s.app_version,
        description="Knoww tells you what meaningfully changed in your watchlist since you last checked, and why it matters.",
        lifespan=lifespan,
        docs_url=f"{s.api_prefix}/docs",
        redoc_url=None,
        openapi_url=f"{s.api_prefix}/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        token = request_id_var.set(rid)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        elapsed = int((time.perf_counter() - started) * 1000)
        response.headers["x-request-id"] = rid
        response.headers["x-content-type-options"] = "nosniff"
        response.headers["x-frame-options"] = "DENY"
        response.headers["referrer-policy"] = "strict-origin-when-cross-origin"
        if not request.url.path.endswith("/health/live"):
            logging.getLogger("knoww.access").info(
                "request",
                extra={"method": request.method, "path": request.url.path, "status": response.status_code, "ms": elapsed, "request_id": rid},
            )
        return response

    register_error_handlers(app)

    from app.api.routes import auth, changes, command_center, misc, stocks, watchlists

    for router in (
        auth.router,
        auth.onboarding,
        command_center.router,
        watchlists.router,
        watchlists.checkpoints,
        changes.router,
        stocks.router,
        misc.market,
        misc.prefs,
        misc.notifications,
        misc.system,
        misc.demo,
    ):
        app.include_router(router, prefix=s.api_prefix)
    return app


app = create_app()
