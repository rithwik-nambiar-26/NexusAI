"""Unit tests for the request-id middleware."""

from __future__ import annotations

from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from nexusai.app.core.middleware import RequestContextMiddleware


async def _echo(request):
    from nexusai.app.core.context import get_request_id

    return JSONResponse({"request_id": get_request_id()})


def _build_app() -> Starlette:
    app = Starlette(routes=[Route("/echo", _echo)])
    app.add_middleware(RequestContextMiddleware, header_name="X-Request-ID")
    return app


def test_generates_request_id_when_absent():
    client = TestClient(_build_app())
    response = client.get("/echo")
    assert response.status_code == 200
    rid = response.json()["request_id"]
    assert rid
    assert response.headers["X-Request-ID"] == rid


def test_preserves_incoming_request_id():
    client = TestClient(_build_app())
    response = client.get("/echo", headers={"X-Request-ID": "trace-42"})
    assert response.json()["request_id"] == "trace-42"
    assert response.headers["X-Request-ID"] == "trace-42"


def test_request_id_available_in_handler():
    client = TestClient(_build_app())
    response = client.get("/echo")
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
