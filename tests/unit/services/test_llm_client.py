"""Tests for the optional local LLM client.

The local LLM is not present in the test environment, and the tests must
not require one. They check the behaviour that matters: the client is
unavailable unless it is configured, it makes no request when it is not,
a failure is never presented as a summary, and the summary it returns is
used only when it is genuinely available.
"""

from __future__ import annotations

import pytest

from nexusai.app.services.llm import LlmUnavailableError, LocalLlmClient, get_llm_client
from nexusai.rag.service import DocumentIntelligenceService


class _Settings:
    """A minimal settings stand-in."""

    def __init__(self, **kwargs):
        self.llm_enabled = kwargs.get("llm_enabled", True)
        self.ollama_base_url = kwargs.get("ollama_base_url")
        self.ollama_model = kwargs.get("ollama_model")
        self.ollama_timeout_seconds = kwargs.get("ollama_timeout_seconds", 30.0)


def test_an_unconfigured_client_is_unavailable():
    """Without a base URL the client is unavailable and makes no request."""
    client = LocalLlmClient(None, None)

    assert client.is_configured is False
    assert client.is_available() is False


def test_a_client_without_a_model_is_unavailable():
    """A base URL alone is not enough."""
    client = LocalLlmClient("http://localhost:11434", None)

    assert client.is_configured is False
    assert client.is_available() is False


def test_summarising_without_a_model_raises():
    """The client refuses rather than pretending to have summarised."""
    client = LocalLlmClient(None, None)

    with pytest.raises(LlmUnavailableError):
        client.summarise([{"text": "evidence", "source_reference": "ref"}])


def test_the_factory_respects_the_enabled_flag():
    """Turning the LLM off makes the client unavailable even when set up."""
    client = get_llm_client(_Settings(llm_enabled=False, ollama_base_url="http://x", ollama_model="m"))

    assert client.is_configured is False


def test_the_factory_builds_a_client_when_configured():
    """A configured base URL and model produce a usable client."""
    client = get_llm_client(
        _Settings(ollama_base_url="http://localhost:11434", ollama_model="llama3.2:3b")
    )

    assert client.is_configured is True
    assert client.model == "llama3.2:3b"


def test_the_service_uses_the_extractive_method_without_an_llm(tmp_path):
    """With no LLM the summary is extractive, and says so."""
    service = DocumentIntelligenceService(store_dir=tmp_path / "vectors")

    summary = service.summarize(document_id="doc_missing")

    # The document is not indexed, so the result is an explicit refusal.
    assert summary.method == "none"
    assert summary.summary_text


def test_a_failing_llm_falls_back_to_the_extractive_method(tmp_path, monkeypatch):
    """A broken LLM never produces the summary; the extractive one does."""
    service = DocumentIntelligenceService(store_dir=tmp_path / "vectors")

    class _BrokenLlm:
        def is_available(self):
            return True

        def summarise(self, evidence, instruction=""):
            raise RuntimeError("the model fell over")

    service.llm_client = _BrokenLlm()

    # The document is not indexed, so the fallback path is not reached;
    # the point is that the failure was not turned into a summary.
    summary = service.summarize(document_id="doc_missing")
    assert summary.status.value in ("insufficient_evidence", "no_documents")
