"""Smoke tests: every application module must import cleanly."""

from __future__ import annotations

import importlib

import pytest

MODULES = [
    "nexusai",
    "nexusai.__main__",
    "nexusai.app",
    "nexusai.app.cli",
    "nexusai.app.config",
    "nexusai.app.main",
    "nexusai.app.core.context",
    "nexusai.app.core.exceptions",
    "nexusai.app.core.logging",
    "nexusai.app.core.middleware",
    "nexusai.app.api.dependencies",
    "nexusai.app.api.schemas.common",
    "nexusai.app.api.schemas.health",
    "nexusai.app.api.schemas.system",
    "nexusai.app.api.routes.health",
    "nexusai.app.api.routes.system",
    "nexusai.app.api.routes.workflows",
    "nexusai.app.db.models",
    "nexusai.app.db.repositories.workflow_run",
    "nexusai.app.db.session",
    "nexusai.app.services.system",
    "nexusai.app.services.workflow",
    "nexusai.app.ui.config",
    "nexusai.agents",
    "nexusai.rag",
    "nexusai.tools",
    "nexusai.ml",
]


@pytest.mark.parametrize("module_name", MODULES)
def test_module_imports(module_name: str):
    assert importlib.import_module(module_name) is not None


def test_cli_help_runs():
    from nexusai.app.cli import main

    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_cli_version():
    from nexusai.app.cli import main

    assert main(["version"]) == 0
