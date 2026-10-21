"""Tests for structured logging and request-id context."""

from __future__ import annotations

import json
import logging
from io import StringIO

from nexusai.app.core.context import get_request_id, set_request_id
from nexusai.app.core.logging import (
    BaseJsonFormatter,
    RequestIdFilter,
    TextFormatter,
    _redact,
    configure_logging,
    get_logger,
)


def test_request_id_context_round_trip():
    set_request_id("abc-123")
    assert get_request_id() == "abc-123"


def test_request_id_default():
    set_request_id("")
    assert get_request_id() == "-"


def test_redact_secret_strings():
    assert _redact("password=secret") == "[REDACTED]"
    # A sensitive key must redact its value even when the value looks benign.
    assert _redact({"api_key": "x"}) == {"api_key": "[REDACTED]"}
    assert _redact({"Authorization": "Bearer abc"}) == {"Authorization": "[REDACTED]"}


def test_redact_passes_through_plain_values():
    assert _redact("hello") == "hello"
    assert _redact([1, 2]) == [1, 2]


def test_text_formatter_includes_request_id():
    configure_logging(level="INFO", log_format="text")
    logger = logging.getLogger("nexusai.test.text")
    handler = logging.StreamHandler(StringIO())
    handler.setFormatter(
        TextFormatter(fmt="%(asctime)s | %(levelname)s | %(request_id)s | %(message)s")
    )
    handler.addFilter(RequestIdFilter())
    logger.handlers = [handler]
    logger.propagate = False
    logger.info("hello")
    out = handler.stream.getvalue()
    assert "hello" in out
    assert "INFO" in out


def test_json_formatter_emits_valid_json():
    configure_logging(level="INFO", log_format="json")
    logger = logging.getLogger("nexusai.test.json")
    handler = logging.StreamHandler(StringIO())
    handler.setFormatter(BaseJsonFormatter())
    handler.addFilter(RequestIdFilter())
    logger.handlers = [handler]
    logger.propagate = False
    logger.info("hello")
    out = handler.stream.getvalue()
    payload = json.loads(out)
    assert payload["message"] == "hello"
    assert payload["level"] == "INFO"
    assert "request_id" in payload


def test_get_logger_returns_scoped_logger():
    logger = get_logger("test")
    assert logger.name == "nexusai.test"


def test_redact_leaves_non_string_values_untouched():
    class Custom:
        def __str__(self) -> str:
            return "custom"

    obj = Custom()
    assert _redact(obj) is obj
    assert _redact(42) == 42
    assert _redact(None) is None


def test_configure_logging_is_idempotent():
    configure_logging(level="DEBUG", log_format="text")
    configure_logging(level="INFO", log_format="text")
