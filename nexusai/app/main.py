"""FastAPI application factory for NexusAI.

The application is built from a single :func:`create_app` factory so that
tests can construct a fresh application with isolated settings and a
temporary database.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import sessionmaker

from nexusai.app.api.routes.execution import router as execution_router
from nexusai.app.api.routes.health import router as health_router
from nexusai.app.api.routes.intent import router as intent_router
from nexusai.app.api.routes.planner import router as planner_router
from nexusai.app.api.routes.rag import router as rag_router
from nexusai.app.api.routes.system import router as system_router
from nexusai.app.api.routes.workflows import router as workflows_router
from nexusai.app.config import REPO_ROOT, Settings, get_settings
from nexusai.app.core.exceptions import register_exception_handlers
from nexusai.app.core.logging import configure_from_settings
from nexusai.app.core.middleware import RequestContextMiddleware
from nexusai.app.db.session import build_engine_and_schema, set_global_engine
from nexusai.app.execution.engine import ExecutionEngine
from nexusai.app.execution.registry import ToolRegistry
from nexusai.app.execution.tools import register_document_tools
from nexusai.app.security.paths import PathPolicy
from nexusai.rag.capabilities import DocumentCapabilities
from nexusai.rag.service import DocumentIntelligenceService


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

    # Build an application-scoped document intelligence service. Each
    # application instance owns its own vector index, so a test application
    # never reads or writes the developer's working index.
    document_service = None
    try:
        store_dir = Path(settings.vector_store_dir)
        if not store_dir.is_absolute():
            store_dir = REPO_ROOT / store_dir

        # Build the filesystem access policy from the configured roots.
        roots = []
        for root in settings.allowed_document_roots:
            root_path = Path(root)
            if not root_path.is_absolute():
                root_path = REPO_ROOT / root_path
            roots.append(root_path)
        path_policy = PathPolicy(roots=roots, base_dir=REPO_ROOT)

        document_service = DocumentIntelligenceService(
            store_dir=store_dir,
            path_policy=path_policy,
        )
    except Exception:
        logging.getLogger("nexusai.app.main").exception(
            "failed to initialise the document intelligence service; the "
            "document endpoints will report the service as unavailable"
        )
        document_service = None

    # Build the tool registry and the execution engine. The registry is
    # populated with the Day 4 document capabilities, so a planner task
    # binds without a translation layer.
    tool_registry = ToolRegistry()
    execution_engine = ExecutionEngine(tool_registry)
    if document_service is not None:
        try:
            register_document_tools(
                tool_registry,
                DocumentCapabilities(document_service),
            )
        except Exception:
            logging.getLogger("nexusai.app.main").exception(
                "failed to register the document tools; the executor will have "
                "no registered capabilities"
            )

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
            {"name": "intent", "description": "Intent classification for user requests."},
            {"name": "planner", "description": "Structured task planning and decomposition."},
            {"name": "documents", "description": "Document ingestion, retrieval and grounded answers."},
            {"name": "execution", "description": "Controlled tool execution of validated plans."},
        ],
    )

    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.document_service = document_service
    app.state.tool_registry = tool_registry
    app.state.execution_engine = execution_engine
    app.state.last_execution_report = None

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
    app.include_router(intent_router)
    app.include_router(planner_router)
    app.include_router(rag_router)
    app.include_router(execution_router)

    return app


def get_app() -> FastAPI:
    """Return the shared application instance (used by ASGI entry points)."""
    return create_app()


__all__ = ["create_app", "get_app"]
