"""Tests for centralised configuration."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from nexusai.app.config import Settings, get_settings, reset_settings_cache


def test_settings_defaults():
    settings = Settings()
    assert settings.app_name == "NexusAI"
    assert settings.app_version == "0.1.0"
    assert settings.environment == "development"
    assert settings.database_url == "sqlite:///./data/nexusai.db"
    assert settings.api_host == "127.0.0.1"
    assert settings.api_port == 8000
    assert settings.log_level == "INFO"
    assert settings.upload_max_size_mb == 25
    assert settings.max_execution_steps == 50
    assert settings.max_retry_budget == 2
    assert settings.max_execution_time_seconds == 300


def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("NEXUSAI_APP_NAME", "TestApp")
    monkeypatch.setenv("NEXUSAI_API_PORT", "9999")
    monkeypatch.setenv("NEXUSAI_LOG_LEVEL", "DEBUG")
    settings = Settings()
    assert settings.app_name == "TestApp"
    assert settings.api_port == 9999
    assert settings.log_level == "DEBUG"


def test_settings_invalid_log_level():
    with pytest.raises(ValidationError):
        Settings(log_level="notalevel")


def test_settings_invalid_upload_limit():
    with pytest.raises(ValidationError):
        Settings(upload_max_size_mb=5000)


def test_settings_database_path_resolves_relative():
    """Relative SQLite paths resolve against the repository root, not the cwd."""
    from nexusai.app.config import REPO_ROOT

    settings = Settings(database_url="sqlite:///./data/nexusai.db")
    resolved = settings.database_path
    assert resolved is not None
    assert resolved == REPO_ROOT / "data" / "nexusai.db"


def test_settings_database_path_none_for_memory():
    settings = Settings(database_url="sqlite:///:memory:")
    assert settings.database_path is None


def test_get_settings_is_cached():
    reset_settings_cache()
    first = get_settings()
    second = get_settings()
    assert first is second
    reset_settings_cache()


def test_settings_no_secret_fields():
    """Settings must not expose any secret material."""
    settings = Settings()
    for value in settings.model_dump().values():
        assert "api_key" not in str(value).lower() or "none" in str(value).lower()
