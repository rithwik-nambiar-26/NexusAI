"""FastAPI application factory for NexusAI.

The application is built from a single :func:`create_app` factory so that
tests can construct a fresh application with isolated settings and a
temporary database.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import sessionmaker

from nexusai.app.api.routes.health import router as health_router
from nexusai.app.api.routes.system import router as system_router
from nexusai.app.api.routes.workflows import router as workflows_router
from nexusai.app.config import Settings, get_settings
from nexusai.app.core.exceptions import register_exception_handlers
from nexusai.app.core.logging import configure_from_settings
from nexusai.app.core.middleware import RequestContextMiddleware
from nexusai.app.db.session import build_engine_and_schema, set_global_engine


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = settings or get_settings()

    configure_from_settings(
        log_level=settings.log_level,
        log_format=settings.log_format,
        log_file=settings.log_file,
    )

    # Build an application-scoped engine. If the database cannot be opened
    # (e.g. an unwritable path), the application still starts and the health
    # endpoint reports the database as unavailable rather than failing.
    engine = None
    session_factory = None
    try:
        engine = build_engine_and_schema(settings)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
        # Keep the module-level factory in sync so the CLI and the Streamlit
        # UI read the same store when they run in this process.
        set_global_engine(engine, session_factory)
    except Exception:
        # Log rather than swallow: a silent except here would hide a broken
        # database configuration behind a permanently "unhealthy" health check.
        logging.getLogger("nexusai.app.main").exception(
            "failed to initialise the database engine; the application will start "
            "with the database reported as unavailable"
        )
        engine = None
        session_factory = None

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "NexusAI: AI-Powered Personal Task Automation — a hybrid workflow "
            "engine that decomposes, executes, verifies and adapts multi-step "
            "everyday tasks."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        contact={"name": "NexusAI (MSc Data Science project)"},
        license_info={"name": "MIT"},
        openapi_tags=[
            {"name": "health", "description": "Liveness and readiness probes."},
            {"name": "system", "description": "Configuration and service availability."},
            {"name": "workflows", "description": "Workflow run persistence."},
        ],
    )

    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.add_middleware(
        RequestContextMiddleware,
        header_name=settings.request_id_header,
    )

    register_exception_handlers(app)

    app.include_router(health_router)
    app.include_router(system_router)
    app.include_router(workflows_router)

    return app


def get_app() -> FastAPI:
    """Return the shared application instance (used by ASGI entry points)."""
    return create_app()


__all__ = ["create_app", "get_app"]
