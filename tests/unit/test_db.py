"""Unit tests for database engine and session management."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from nexusai.app.config import Settings
from nexusai.app.db.models import Base, ExecutionStep, WorkflowRun
from nexusai.app.db.session import (
    create_engine_from_settings,
    get_db_standalone,
    init_db,
    reset_engine,
)


def test_engine_created_for_sqlite_file(tmp_path: Path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'x.db'}")
    engine = create_engine_from_settings(settings)
    assert engine.dialect.name == "sqlite"
    engine.dispose()


def test_init_db_creates_tables(tmp_path: Path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'y.db'}")
    engine = init_db(settings)
    with engine.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        }
    assert "workflow_runs" in tables
    assert "execution_steps" in tables
    engine.dispose()
    reset_engine()


def test_models_define_expected_tables():
    assert WorkflowRun.__tablename__ == "workflow_runs"
    assert ExecutionStep.__tablename__ == "execution_steps"
    assert "workflow_runs" in Base.metadata.tables
    assert "execution_steps" in Base.metadata.tables


def test_get_db_standalone_yields_session(tmp_path: Path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'z.db'}")
    engine = init_db(settings)
    generator = get_db_standalone()
    session = next(generator)
    assert isinstance(session, Session)
    generator.close()
    engine.dispose()
    reset_engine()


def test_relationship_cascade_configured():
    assert WorkflowRun.steps.property.cascade is not None
    assert "delete-orphan" in WorkflowRun.steps.property.cascade
