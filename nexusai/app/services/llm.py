"""The optional local LLM backend.

NexusAI can use a locally-run Ollama model to write a summary. The model
is optional in every sense:

* it is not configured by default, and no request is made unless a base
  URL is set;
* when it is configured but not running, the call fails and the caller
  falls back to the extractive summariser;
* the caller is told which method produced the summary, so a summary is
  never presented as generated when it was extracted.

Nothing here reaches a paid API or a hosted service. The base URL is
expected to be a local process.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from nexusai.app.core.logging import get_logger

logger = get_logger("llm.client")

#: The system prompt used for summarisation. It states the constraint that
#: matters: the model may only use the supplied evidence.
_SUMMARY_SYSTEM_PROMPT = (
    "You summarise documents for a research system. Use ONLY the evidence "
    "supplied below. Do not add facts, decisions, owners or dates that are "
    "not in the evidence. If the evidence does not support a summary, say "
    "that the evidence is insufficient. "
    "Reply with JSON and nothing else, in exactly this shape: "
    '{"overview": "...", "decisions": ["..."], "action_items": ["..."], '
    '"sufficient": true}. '
    "Use an empty list for a section that the evidence does not support, "
    "and set sufficient to false when the evidence does not support a "
    "summary at all."
)


class LlmUnavailableError(RuntimeError):
    """Raised when the local LLM cannot be used."""


@dataclass
class LlmSummary:
    """A summary produced by the local LLM.

    Attributes:
        overview: The prose overview.
        decisions: The decisions the evidence supports.
        action_items: The action items the evidence supports.
        sufficient: False when the model said the evidence was insufficient.
        model: The model that produced it.
    """

    overview: str = ""
    decisions: list[str] = None  # type: ignore[assignment]
    action_items: list[str] = None  # type: ignore[assignment]
    sufficient: bool = True
    model: str = ""

    def __post_init__(self) -> None:
        if self.decisions is None:
            self.decisions = []
        if self.action_items is None:
            self.action_items = []


class LocalLlmClient:
    """A client for a locally-run Ollama server.

    Args:
        base_url: The Ollama server's base URL. When it is None the
            client reports itself unavailable and makes no request.
        model: The model to use.
        timeout_seconds: How long to wait for one request.
    """

    def __init__(
        self,
        base_url: str | None,
        model: str | None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/") or None
        self.model = model
        self.timeout_seconds = timeout_seconds

    @property
    def is_configured(self) -> bool:
        """True when a base URL and a model have been supplied."""
        return bool(self.base_url and self.model)

    def is_available(self) -> bool:
        """True when the client is configured and the server answers.

        This makes a request, so it is not called on a hot path. It is
        used to decide which summarisation method to use, and the answer
        is cached for the life of the client.
        """
        if not self.is_configured:
            return False
        if getattr(self, "_available", None) is not None:
            return bool(self._available)
        try:
            response = httpx.get(
                f"{self.base_url}/api/tags",
                timeout=min(self.timeout_seconds, 5.0),
            )
            self._available = response.status_code == 200
        except Exception:
            self._available = False
        if not self._available:
            logger.info(
                "The local LLM is configured but not answering; the "
                "extractive summariser will be used instead",
                extra={"base_url": self.base_url},
            )
        return bool(self._available)

    def summarise(self, evidence: list[dict[str, Any]], instruction: str = "") -> LlmSummary:
        """Summarise the supplied evidence.

        Args:
            evidence: The passages to summarise. Each carries at least
                ``text`` and ``source_reference``.
            instruction: What the summary should focus on.

        Returns:
            The model's summary.

        Raises:
            LlmUnavailableError: When the model cannot be used, or its
                reply cannot be understood.
        """
        if not self.is_available():
            raise LlmUnavailableError("The local LLM is not available.")

        body = self._build_prompt(evidence, instruction)
        try:
            response = httpx.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "stream": False,
                    "format": "json",
                    "messages": [
                        {"role": "system", "content": _SUMMARY_SYSTEM_PROMPT},
                        {"role": "user", "content": body},
                    ],
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise LlmUnavailableError(f"The local LLM request failed: {exc}") from exc

        content = _extract_content(payload)
        try:
            parsed = json.loads(content)
        except (TypeError, ValueError) as exc:
            raise LlmUnavailableError(
                "The local LLM did not return JSON that could be read."
            ) from exc

        if not isinstance(parsed, dict):
            raise LlmUnavailableError("The local LLM returned an unexpected shape.")

        return LlmSummary(
            overview=str(parsed.get("overview") or "").strip(),
            decisions=[str(item).strip() for item in parsed.get("decisions") or [] if str(item).strip()],
            action_items=[
                str(item).strip() for item in parsed.get("action_items") or [] if str(item).strip()
            ],
            sufficient=bool(parsed.get("sufficient", True)),
            model=str(self.model or ""),
        )

    @staticmethod
    def _build_prompt(evidence: list[dict[str, Any]], instruction: str) -> str:
        """Build the user message from the evidence."""
        parts = []
        if instruction:
            parts.append(f"Focus: {instruction}\n")
        parts.append("Evidence:")
        for item in evidence:
            reference = item.get("source_reference", "")
            text = item.get("text", "")
            parts.append(f"\n[{reference}]\n{text}")
        return "\n".join(parts)


def _extract_content(payload: dict[str, Any]) -> str:
    """Pull the assistant's text out of an Ollama chat response."""
    message = payload.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
    response = payload.get("response")
    if isinstance(response, str):
        return response
    return ""


def get_llm_client(settings) -> LocalLlmClient:
    """Return a client for the configured local LLM.

    When the local LLM is disabled, or no base URL is configured, the
    returned client reports itself unavailable and makes no request.
    """
    if not getattr(settings, "llm_enabled", True):
        return LocalLlmClient(None, None)
    return LocalLlmClient(
        getattr(settings, "ollama_base_url", None),
        getattr(settings, "ollama_model", None),
        float(getattr(settings, "ollama_timeout_seconds", 30.0)),
    )
