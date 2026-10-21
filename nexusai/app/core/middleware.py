"""Request-context middleware: correlation IDs and per-request logging."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from nexusai.app.core.context import get_request_id, set_request_id

logger = logging.getLogger("nexusai.app.core.middleware")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns/propagates a correlation id per request.

    Behaviour:
    * Reads ``X-Request-ID`` from inbound headers when present, otherwise
      generates a UUID4.
    * Makes the id available via ``nexusai.app.core.context.get_request_id``
      for the duration of the request (structured logs include it).
    * Echoes the id back on the response header so clients can correlate.
    """

    def __init__(self, app: ASGIApp, header_name: str = "X-Request-ID") -> None:
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        incoming = request.headers.get(self.header_name)
        request_id = incoming if incoming else uuid.uuid4().hex
        set_request_id(request_id)

        response = await call_next(request)
        response.headers[self.header_name] = request_id
        logger.debug(
            "request %s %s -> %s",
            request.method,
            request.url.path,
            response.status_code,
            extra={"request_id": request_id},
        )
        return response


def request_id_dependency(request: Request) -> str:
    """FastAPI dependency exposing the current request id to route handlers."""
    return get_request_id()
