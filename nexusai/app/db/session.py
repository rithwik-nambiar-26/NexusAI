"""Engine and session management for SQLite persistence."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from fastapi import Request
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from nexusai.app.config import REPO_ROOT, Settings, get_settings
from nexusai.app.core.exceptions import ServiceUnavailableError

_engine: Engine | None = None
_session_factory: sessionmaker | None = None


def _sqlite_path(settings: Settings) -> Path | None:
    """Return the on-disk SQLite path for a relative URL, else None.

    Relative paths are resolved against the repository root (not the current
    working directory) so the store is stable regardless of where a command
    is launched from. In-memory databases return ``None``.
    """
    if not settings.database_url.startswith("sqlite:///"):
        return None
    raw = settings.database_url.split(":///", 1)[1]
    if raw in {":memory:", ""}:
        return None
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate
    return REPO_ROOT / candidate


def _ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def create_engine_from_settings(settings: Settings) -> Engine:
    """Create a SQLAlchemy engine for the given settings.

    SQLite is the default local-first store. ``:memory:`` databases are
    created per-connection so that tests never touch a real database.
    """
    if settings.database_url.startswith("sqlite"):
        path = _sqlite_path(settings)
        if path is not None:
            _ensure_parent_dir(path)
        kwargs: dict = {
            "url": settings.database_url,
            "future": True,
        }
        if path is None:
            # In-memory database: share a single connection across threads so
            # that the schema created at init time is visible to every request.
            kwargs["connect_args"] = {"check_same_thread": False}
            kwargs["poolclass"] = StaticPool
        engine = create_engine(**kwargs)
    else:
        engine = create_engine(
            url=settings.database_url,
            future=True,
            pool_pre_ping=True,
        )

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):  # pragma: no cover
        if path is not None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
            finally:
                cursor.close()

    return engine


def build_engine_and_schema(settings: Settings) -> Engine:
    """Create an engine for *settings* and ensure the schema exists.

    This does not touch the module-level globals; it is used by the FastAPI
    application factory so that each application instance owns its engine.
    """
    from nexusai.app.db.models import Base

    engine = create_engine_from_settings(settings)
    Base.metadata.create_all(bind=engine)
    return engine


def init_db(settings: Settings | None = None) -> Engine:
    """Initialise the global engine and create the schema."""
    global _engine, _session_factory
    settings = settings or get_settings()
    engine = build_engine_and_schema(settings)
    _engine = engine
    _session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return engine


def get_engine() -> Engine:
    """Return the configured engine, initialising it lazily if needed."""
    global _engine
    if _engine is None:
        _engine = init_db(get_settings())
    return _engine


def get_session_factory() -> sessionmaker:
    """Return the configured session factory."""
    global _session_factory
    if _session_factory is None:
        init_db(get_settings())
    return _session_factory  # type: ignore[return-value]


def get_db(request: Request) -> Generator[Session, None, None]:
    """FastAPI dependency yielding an application-scoped session.

    The session is bound to the engine attached to the running application,
    so an application built with a test database never touches a real one.
    """
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise ServiceUnavailableError(
            "database is not initialised for this application instance",
            code="database_unavailable",
        )
    session = factory()
    try:
        yield session
    finally:
        session.close()


def get_db_standalone() -> Generator[Session, None, None]:
    """Yield a session from the global factory (CLI / UI use)."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def set_global_engine(engine: Engine, factory: sessionmaker) -> None:
    """Register an application-scoped engine as the process-wide default."""
    global _engine, _session_factory
    _engine = engine
    _session_factory = factory


def reset_engine() -> None:
    """Reset the global engine/session factory (tests only)."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
