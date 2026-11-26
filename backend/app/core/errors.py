from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import log_event, request_id_var


class DomainError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class NotFound(DomainError):
    status_code = 404
    code = "not_found"


class Conflict(DomainError):
    status_code = 409
    code = "conflict"


class Unauthorized(DomainError):
    status_code = 401
    code = "unauthorized"


class RateLimited(DomainError):
    status_code = 429
    code = "rate_limited"


def _body(code: str, message: str, **extra) -> dict:
    return {"error": {"code": code, "message": message, "request_id": request_id_var.get(), **extra}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain(_: Request, exc: DomainError):
        return JSONResponse(_body(exc.code, exc.message), status_code=exc.status_code)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        return JSONResponse(_body("http_error", str(exc.detail)), status_code=exc.status_code, headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        fields = [{"loc": [str(p) for p in e.get("loc", [])], "msg": e.get("msg")} for e in exc.errors()]
        return JSONResponse(_body("validation_error", "Invalid request", fields=fields), status_code=422)

    @app.exception_handler(OperationalError)
    async def _db(_: Request, exc: OperationalError):
        log_event("database.unavailable", logging.ERROR, error=type(exc).__name__)
        return JSONResponse(_body("service_unavailable", "The database is temporarily unavailable. Please retry."), status_code=503)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        logging.getLogger("knoww").exception("unhandled_error")
        return JSONResponse(_body("internal_error", "Something went wrong. It has been logged."), status_code=500)
