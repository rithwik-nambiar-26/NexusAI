"""Intent classification service for NexusAI.

Provides high-level intent classification with structured output,
integrating with NexusAI's existing service architecture.
"""

from __future__ import annotations

from typing import Any

from nexusai.app.core.exceptions import ServiceUnavailableError
from nexusai.app.core.logging import get_logger
from nexusai.ml.classifier import IntentClassifier, get_classifier, reset_classifier
from nexusai.ml.schemas import (
    IntentCategory,
    IntentClassificationRequest,
    IntentClassificationResult,
)

logger = get_logger("ml.intent_service")


class IntentClassificationService:
    """Service wrapper for intent classification.

    Provides a clean interface for the API and workflow system
    to classify user requests into intent categories.
    """

    def __init__(self, classifier: IntentClassifier | None = None):
        self._classifier = classifier or get_classifier()

    def classify(self, request: IntentClassificationRequest) -> IntentClassificationResult:
        """Classify a user request into an intent category.

        Args:
            request: The classification request with user text

        Returns:
            Structured classification result

        Raises:
            ServiceUnavailableError: If the model is not available
        """
        if not self._classifier.is_ready():
            raise ServiceUnavailableError(
                "Intent classifier not trained or loaded. Run training first.",
                code="model_unavailable",
            )

        result = self._classifier.predict(request)

        logger.info(
            "Intent classified",
            extra={
                "intent": result.predicted_intent.value if result.predicted_intent else None,
                "confidence": result.confidence,
                "status": result.status.value,
            },
        )

        return result

    def classify_text(self, text: str, context: dict[str, Any] | None = None) -> IntentClassificationResult:
        """Convenience method to classify plain text.

        Args:
            text: User request text
            context: Optional context from conversation

        Returns:
            Structured classification result
        """
        request = IntentClassificationRequest(text=text, context=context)
        return self.classify(request)

    def is_available(self) -> bool:
        """Check if the classifier is trained and ready."""
        return self._classifier.is_ready()

    def get_supported_intents(self) -> list[IntentCategory]:
        """Return list of intents that map to supported workflows."""
        return IntentCategory.supported()

    def get_all_intents(self) -> list[IntentCategory]:
        """Return all known intent categories."""
        return list(IntentCategory)


# Global service instance
_service: IntentClassificationService | None = None


def get_intent_service() -> IntentClassificationService:
    """Get or create the global intent classification service."""
    global _service
    if _service is None:
        _service = IntentClassificationService()
    return _service


def reset_intent_service() -> None:
    """Reset global service (for testing)."""
    global _service
    _service = None
    reset_classifier()
