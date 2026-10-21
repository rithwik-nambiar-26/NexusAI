"""Structured application logging.

Two formatters are provided: ``text`` for local development and ``json`` for
production/local-first deployment where logs are consumed by log tooling.
Sensitive values (anything whose key mentions password/secret/token/etc.) are
always redacted so secrets never reach the log output.
"""

from __future__ import annotations

import json
import logging
import logging.config
import re
from datetime import UTC, datetime
from typing import Any

from nexusai.app.core.context import get_request_id

LOG_LEVELS = ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET")

_SECRET_KEY = re.compile(
    r"(password|passwd|secret|token|api_key|apikey|authorization|credentials)",
    re.IGNORECASE,
)

_LOG_RECORD_RESERVED = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__.keys())


def _redact(value: Any, key: str | None = None) -> Any:
    if isinstance(value, str) and (
        _SECRET_KEY.search(str(value)) or (key is not None and _SECRET_KEY.search(key))
    ):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {k: _redact(v, key=k) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return type(value)(_redact(v) for v in value)  # type: ignore[call-arg]
    return value


class BaseJsonFormatter(logging.Formatter):
    """Emit one JSON object per log record."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key in _LOG_RECORD_RESERVED or key in ("request_id",):
                continue
            if not key.startswith("_"):
                payload[key] = _redact(value)
        return json.dumps(payload, default=str)


class TextFormatter(logging.Formatter):
    """Plain text formatter including request id and UTC timestamp."""

    def formatTime(self, record: logging.LogRecord, datefmt=None) -> str:  # noqa: N802
        return datetime.fromtimestamp(record.created, UTC).isoformat()

    def format(self, record: logging.LogRecord) -> str:
        record.asctime = self.formatTime(record)
        record.request_id = getattr(record, "request_id", "-")
        message = super().format(record)
        if record.exc_info:
            message += "\n" + self.formatException(record.exc_info)
        return message


class RequestIdFilter(logging.Filter):
    """Inject the active request id into every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


def _formatter_name(log_format: str) -> str:
    return "json" if log_format == "json" else "text"


def configure_logging(
    *,
    level: str = "INFO",
    log_format: str = "text",
    log_file: str | None = None,
) -> None:
    """Configure root and uvicorn loggers.

    Idempotent: calling more than once replaces the handler configuration.
    """
    level = level.upper()
    formatter = _formatter_name(log_format)
    handlers: list[str] = ["console"]
    if log_file:
        handlers.append("file")

    config: dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {"()": BaseJsonFormatter},
            "text": {
                "()": TextFormatter,
                "format": "%(asctime)s | %(levelname)-8s | %(request_id)-13s | %(name)s: %(message)s",
            },
        },
        "filters": {"request_id": {"()": RequestIdFilter}},
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
                "formatter": formatter,
                "filters": ["request_id"],
            },
        },
        "loggers": {
            "nexusai": {"level": level, "handlers": handlers, "propagate": False},
            "uvicorn": {"level": level, "handlers": handlers, "propagate": False},
            "uvicorn.error": {"level": level, "handlers": handlers, "propagate": False},
            "uvicorn.access": {"level": level, "handlers": handlers, "propagate": False},
        },
        "root": {"level": level, "handlers": handlers},
    }
    if log_file:
        config["handlers"]["file"] = {
            "class": "logging.FileHandler",
            "filename": log_file,
            "formatter": formatter,
            "filters": ["request_id"],
            "encoding": "utf-8",
        }
    logging.config.dictConfig(config)


def get_logger(name: str) -> logging.Logger:
    """Return a logger scoped to *name*; logging is configured on demand."""
    return logging.getLogger(f"nexusai.{name}")


def configure_from_settings(log_level: str, log_format: str, log_file: str | None) -> None:
    """Public entry point used by ``create_app`` and the CLI."""
    configure_logging(level=log_level, log_format=log_format, log_file=log_file)
