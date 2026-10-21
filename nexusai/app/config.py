"""Centralised, validated application settings.

Values can be overridden through environment variables prefixed with
``NEXUSAI_`` or through a ``.env`` file at the repository root. ``.env`` is
gitignored and never committed; none of these values may be secrets.

The :class:`Settings` class is the single source of truth for configuration.
Everything else reads settings from the FastAPI application state or, in
non-HTTP contexts, from :func:`get_settings`.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

try:  # pragma: no cover - resolved at import time
    from pydantic import PositiveInt
except ImportError:  # pragma: no cover - older pydantic 2.x shim
    PositiveInt = int  # type: ignore[assignment,misc]

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="NEXUSAI_",
        env_ignore_empty=True,
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application -------------------------------------------------------
    app_name: str = "NexusAI"
    app_version: str = "0.1.0"
    environment: Literal["development", "testing", "production"] = "development"
    debug: bool = False

    # --- Database ----------------------------------------------------------
    # SQLite is the default local-first store. Relative file paths are
    # resolved against the repository root.
    database_url: str = "sqlite:///./data/nexusai.db"

    # --- Document intelligence ---------------------------------------------
    # Directory holding the local vector index. Relative paths are
    # resolved against the repository root.
    vector_store_dir: str = "./artifacts/vectors"

    # --- Filesystem access policy -------------------------------------------
    # Directories that may be read from disk. Every path reaching the
    # filesystem is resolved and checked against these roots, so a caller
    # cannot read a file outside them. Relative roots are resolved
    # against the repository root.
    allowed_document_roots: list[str] = Field(
        default_factory=lambda: ["./data", "./docs", "./experiments"]
    )

    # --- API server --------------------------------------------------------
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:8501"])

    # --- Logging -----------------------------------------------------------
    log_level: str = "INFO"
    log_format: Literal["text", "json"] = "text"
    log_file: str | None = None

    # --- Request handling --------------------------------------------------
    request_id_header: str = "X-Request-ID"

    # --- Upload / execution limits -----------------------------------------
    upload_max_size_mb: PositiveInt = 25
    max_execution_steps: PositiveInt = 50
    max_retry_budget: PositiveInt = 2
    max_execution_time_seconds: PositiveInt = 300

    # --- Optional local services (probed honestly; never assumed) ----------
    service_probe_timeout_seconds: PositiveInt = 1

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:

        if value.upper() not in (
            "CRITICAL",
            "ERROR",
            "WARNING",
            "INFO",
            "DEBUG",
            "NOTSET",
        ):
            raise ValueError(f"invalid log_level: {value!r}")
        return value.upper()

    @field_validator("upload_max_size_mb")
    @classmethod
    def _validate_upload_limit(cls, value: int) -> int:
        if value > 1024:
            raise ValueError("upload_max_size_mb must not exceed 1024")
        return value

    @property
    def database_path(self) -> Path | None:
        """Resolve a relative SQLite file path against the repo root, if any.

        Returns ``None`` for in-memory databases and for non-SQLite URLs.
        """
        if not self.database_url.startswith("sqlite:///"):
            return None
        raw = self.database_url.split(":///", 1)[1]
        if raw in {":memory:", ""}:
            return None
        candidate = Path(raw)
        if candidate.is_absolute():
            return candidate
        return REPO_ROOT / candidate


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance."""
    return Settings()


def reset_settings_cache() -> None:
    """Clear the settings cache (tests only)."""
    get_settings.cache_clear()  # type: ignore[attr-defined]
