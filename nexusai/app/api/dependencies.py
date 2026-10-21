"""API dependencies: settings, database session, request id."""

from __future__ import annotations

from fastapi import Request

from nexusai.app.config import Settings
from nexusai.app.core.context import get_request_id
from nexusai.app.db.session import get_db


def get_app_settings(request: Request) -> Settings:
    """Return the settings attached to the application instance.

    Using this instead of the global ``get_settings`` cache guarantees that
    routes probe the same database and configuration the application was
    built with.
    """
    return request.app.state.settings


def get_request_id_dep(request: Request) -> str:
    """FastAPI dependency exposing the current request id to route handlers."""
    return get_request_id()


__all__ = [
    "get_app_settings",
    "get_db",
    "get_request_id",
    "get_request_id_dep",
]
