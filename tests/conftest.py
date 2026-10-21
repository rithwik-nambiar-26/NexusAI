"""Shared pytest fixtures.

Tests use an isolated in-memory SQLite database so they never touch a real
database. All external dependencies are mocked; no test requires a live LLM,
paid API or public internet connection.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure the package is importable without installation.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nexusai.app.config import Settings, reset_settings_cache
from nexusai.app.db.session import init_db, reset_engine


@pytest.fixture()
def tmp_db_path(tmp_path: Path) -> str:
    """Return a temporary SQLite file path."""
    return str(tmp_path / "test_nexusai.db")


@pytest.fixture()
def isolated_settings(tmp_db_path: str) -> Settings:
    """Settings pointing at a temporary, isolated SQLite database."""
    reset_settings_cache()
    reset_engine()
    settings = Settings(
        database_url=f"sqlite:///{tmp_db_path}",
        environment="testing",
        debug=False,
    )
    return settings


@pytest.fixture()
def app_factory():
    """A factory that builds a FastAPI app with isolated settings."""
    from nexusai.app.main import create_app

    def _build(settings: Settings):
        return create_app(settings=settings)

    return _build


@pytest.fixture()
def client_factory(app_factory, isolated_settings):
    """A factory that builds a TestClient with isolated settings."""
    from fastapi.testclient import TestClient

    def _build(settings: Settings | None = None):
        settings = settings or isolated_settings
        return TestClient(app_factory(settings))

    return _build


@pytest.fixture()
def client(client_factory):
    """A ready-to-use TestClient backed by an isolated in-memory database."""
    return client_factory()


@pytest.fixture()
def db_session(isolated_settings):
    """Yield a SQLAlchemy session bound to an isolated database."""
    engine = init_db(isolated_settings)
    from sqlalchemy.orm import Session

    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def autocommit_session(db_session):
    """A session that auto-commits on teardown (convenience for tests)."""
    yield db_session
    db_session.commit()


@pytest.fixture()
def isolated_env(tmp_path, monkeypatch):
    """Isolate environment variables for the duration of a test."""
    monkeypatch.setenv("NEXUSAI_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("NEXUSAI_ENVIRONMENT", "testing")
    monkeypatch.setenv("NEXUSAI_DEBUG", "false")
    reset_settings_cache()
    reset_engine()
    yield
    reset_settings_cache()
    reset_engine()


@pytest.fixture(autouse=True)
def _reset_global_state():
    """Reset global engine/settings state after every test."""
    yield
    reset_settings_cache()
    reset_engine()
