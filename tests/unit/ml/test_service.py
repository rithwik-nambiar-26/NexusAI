"""Tests for intent classification service."""

from __future__ import annotations

import pytest

from nexusai.app.core.exceptions import ServiceUnavailableError
from nexusai.app.services.intent import IntentClassificationService, reset_intent_service
from nexusai.ml.classifier import IntentClassifier, reset_classifier
from nexusai.ml.schemas import (
    IntentClassificationRequest,
)


@pytest.fixture(autouse=True)
def _reset():
    """Reset services between tests."""
    reset_classifier()
    reset_intent_service()
    yield
    reset_classifier()
    reset_intent_service()


def test_service_initialization():
    """Test service can be initialized."""
    clf = IntentClassifier()
    service = IntentClassificationService(classifier=clf)
    assert service._classifier is clf


def test_service_default_classifier():
    """Test service uses default classifier if none provided."""
    service = IntentClassificationService()
    assert service._classifier is not None


def test_service_classify_no_model():
    """Test classification fails when model not available."""
    clf = IntentClassifier()
    service = IntentClassificationService(classifier=clf)

    req = IntentClassificationRequest(text="Test request")
    with pytest.raises(ServiceUnavailableError) as exc_info:
        service.classify(req)

    assert exc_info.value.code == "model_unavailable"
    assert "not trained" in str(exc_info.value).lower()


def test_service_classify_with_model():
    """Test classification with trained model."""
    clf = IntentClassifier()

    train_texts = [
        "Summarize this document",
        "What is in the manual?",
        "Analyze the sales data",
    ]
    train_labels = [
        "document_summarisation",
        "document_question_answering",
        "data_analysis",
    ]
    clf.train(train_texts, train_labels)

    service = IntentClassificationService(classifier=clf)

    req = IntentClassificationRequest(text="Summarize the report")
    result = service.classify(req)

    assert result.predicted_intent == "document_summarisation"
    assert result.confidence > 0
    assert result.status in ("confident", "low_confidence", "clarification_required")


def test_service_classify_text_convenience():
    """Test classify_text convenience method."""
    clf = IntentClassifier()

    # Need at least 2 classes with at least 2 samples each for LogisticRegression
    train_texts = [
        "Summarize this document",
        "Give me a summary of the report",
        "What is in the manual?",
        "What does the manual say?",
    ]
    train_labels = [
        "document_summarisation",
        "document_summarisation",
        "document_question_answering",
        "document_question_answering",
    ]
    clf.train(train_texts, train_labels)

    service = IntentClassificationService(classifier=clf)

    result = service.classify_text("Summarize the report")
    assert result.predicted_intent == "document_summarisation"


def test_service_is_available():
    """Test is_available method."""
    clf = IntentClassifier()
    service = IntentClassificationService(classifier=clf)

    assert service.is_available() is False

    # Need at least 2 classes with at least 2 samples each for LogisticRegression
    clf.train(
        ["test one", "test two", "test three", "test four"],
        ["document_summarisation", "document_summarisation", "document_question_answering", "document_question_answering"]
    )
    assert service.is_available() is True


def test_service_get_supported_intents():
    """Test get_supported_intents method."""
    service = IntentClassificationService()
    supported = service.get_supported_intents()

    assert len(supported) == 7
    assert "document_question_answering" in [i.value for i in supported]
    assert "document_summarisation" in [i.value for i in supported]
    assert "destructive_operation" not in [i.value for i in supported]
    assert "channel_unavailable" not in [i.value for i in supported]


def test_service_get_all_intents():
    """Test get_all_intents method."""
    service = IntentClassificationService()
    all_intents = service.get_all_intents()

    assert len(all_intents) == 12