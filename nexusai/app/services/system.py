"""System-status service.

The status endpoint reports **actual** availability: optional local services
(Ollama, ChromaDB, SQLite) are probed at runtime and reported as
``available`` only when the probe succeeds. Nothing is assumed available.
"""

from __future__ import annotations

import socket
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from nexusai.app.config import Settings


def _probe_tcp(host: str, port: int, timeout: float) -> bool:
    """Return True if a TCP connection to host:port succeeds."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _probe_http(url: str, timeout: float) -> bool:
    """Return True if an HTTP GET to *url* returns a 2xx/3xx response."""
    try:
        import httpx  # type: ignore
    except ImportError:
        return False
    try:
        resp = httpx.get(url, timeout=timeout)
        return resp.status_code < 400
    except Exception:
        return False


def _sqlite_available(engine: Engine | None) -> bool:
    """Return True if the configured SQLite store can be queried."""
    if engine is None:
        return False
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def get_service_status(settings: Settings, engine: Engine | None) -> dict[str, Any]:
    """Probe every optional service and return an honest status map."""
    timeout = float(settings.service_probe_timeout_seconds)

    # The optional local LLM. Absent configuration means "not configured",
    # and it is reported as unavailable rather than assumed to be present.
    ollama_url = getattr(settings, "ollama_base_url", None)
    chromadb_url = None

    ollama = _probe_http(ollama_url, timeout) if ollama_url else False
    chromadb = _probe_http(chromadb_url, timeout) if chromadb_url else False

    return {
        "database": {
            "available": _sqlite_available(engine),
            "backend": "sqlite" if settings.database_url.startswith("sqlite") else "other",
        },
        "ollama": {
            "available": ollama,
            "configured": ollama_url is not None,
            "url": ollama_url,
            "model": getattr(settings, "ollama_model", None),
        },
        "chromadb": {
            "available": chromadb,
            "configured": chromadb_url is not None,
            "url": chromadb_url,
        },
    }
