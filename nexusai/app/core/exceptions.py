"""Application error model and centralised exception handling.

* ``NexusAIError`` is the base for all recoverable application errors. It
  carries a stable error code, an optional detail payload, and an optional
  HTTP status code.
* :func:`register_exception_handlers` converts both NexusAIError and raw
  exceptions into a consistent JSON error shape without ever leaking internal
  stack traces to API consumers.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class NexusAIError(Exception):
    """Base class for application errors with a stable contract."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        code: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code

    def to_dict(self, request_id: str) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            },
            "request_id": request_id,
        }


class ConfigurationError(NexusAIError):
    status_code = 500
    code = "configuration_error"


class NotFoundError(NexusAIError):
    status_code = 404
    code = "not_found"


class ServiceUnavailableError(NexusAIError):
    status_code = 503
    code = "service_unavailable"


class ValidationError(NexusAIError):
    status_code = 400
    code = "validation_error"


def _error_response(
    status_code: int,
    code: str,
    message: str,
    request_id: str,
    *,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        },
        "request_id": request_id,
    }


def register_exception_handlers(app) -> None:
    """Register consistent JSON error handlers on *app*."""

    from nexusai.app.core.context import get_request_id

    @app.exception_handler(NexusAIError)
    async def _handle_nexus_error(request: Request, exc: NexusAIError) -> JSONResponse:
        request_id = get_request_id()
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_dict(request_id),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        request_id = get_request_id()
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_response(
                exc.status_code,
                f"http_{exc.status_code}",
                str(exc.detail),
                request_id,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = get_request_id()
        return JSONResponse(
            status_code=422,
            content=_error_response(
                422,
                "validation_error",
                "request validation failed",
                request_id,
                details={"errors": exc.errors()},
            ),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        request_id = get_request_id()
        # Log the full traceback locally; never send it to the client.
        logger = logging.getLogger("nexusai.app.core.exceptions")
        logger.exception("unhandled exception during request %s", request_id)
        return JSONResponse(
            status_code=500,
            content=_error_response(
                500,
                "internal_error",
                "an unexpected error occurred",
                request_id,
            ),
        )


import logging  # noqa: E402  (imported here to keep exception-handler registration above)
