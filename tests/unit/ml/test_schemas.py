"""Tests for intent classification schemas."""

from __future__ import annotations

import pytest

from nexusai.ml.schemas import (
    ClassificationStatus,
    IntentCategory,
    IntentClassificationRequest,
    IntentClassificationResult,
)


def test_intent_category_values():
    """Test that all expected intent categories exist."""
    expected = {
        "document_question_answering",
        "document_summarisation",
        "data_analysis",
        "research",
        "communication",
        "document_operation",
        "destructive_operation",
        "invalid",
        "infeasible",
        "out_of_scope",
    }
    actual = {c.value for c in IntentCategory}
    assert actual == expected


def test_intent_category_supported():
    """Test supported() returns correct intents."""
    supported = IntentCategory.supported()
    assert IntentCategory.DOCUMENT_QUESTION_ANSWERING in supported
    assert IntentCategory.DOCUMENT_SUMMARISATION in supported
    assert IntentCategory.DATA_ANALYSIS in supported
    assert IntentCategory.RESEARCH in supported
    assert IntentCategory.COMMUNICATION in supported
    assert IntentCategory.DOCUMENT_OPERATION in supported
    assert IntentCategory.DESTRUCTIVE_OPERATION not in supported
    assert IntentCategory.INVALID not in supported
    assert IntentCategory.INFEASIBLE not in supported
    assert IntentCategory.OUT_OF_SCOPE not in supported


def test_intent_category_special():
    """Test special() returns correct intents."""
    special = IntentCategory.special()
    assert IntentCategory.DESTRUCTIVE_OPERATION in special
    assert IntentCategory.INVALID in special
    assert IntentCategory.INFEASIBLE in special
    assert IntentCategory.OUT_OF_SCOPE in special
    assert IntentCategory.DOCUMENT_QUESTION_ANSWERING not in special


def test_classification_status_values():
    """Test classification status enum values."""
    assert ClassificationStatus.CONFIDENT == "confident"
    assert ClassificationStatus.LOW_CONFIDENCE == "low_confidence"
    assert ClassificationStatus.CLARIFICATION_REQUIRED == "clarification_required"
    assert ClassificationStatus.ABSTAINED == "abstained"
    assert ClassificationStatus.ERROR == "error"


def test_intent_classification_request_validation():
    """Test request validation."""
    # Valid request
    req = IntentClassificationRequest(text="Summarize this document")
    assert req.text == "Summarize this document"

    # Empty text should fail
    with pytest.raises(ValueError):
        IntentClassificationRequest(text="")

    # Too long text should fail
    with pytest.raises(ValueError):
        IntentClassificationRequest(text="x" * 2001)


def test_intent_classification_result_is_actionable():
    """Test is_actionable() method."""
    result = IntentClassificationResult(
        original_request="test",
        predicted_intent=IntentCategory.DOCUMENT_QUESTION_ANSWERING,
        confidence=0.9,
        status=ClassificationStatus.CONFIDENT,
    )
    assert result.is_actionable() is True

    result = IntentClassificationResult(
        original_request="test",
        predicted_intent=IntentCategory.INVALID,
        confidence=0.9,
        status=ClassificationStatus.CONFIDENT,
    )
    assert result.is_actionable() is False

    result = IntentClassificationResult(
        original_request="test",
        predicted_intent=None,
        confidence=0.0,
        status=ClassificationStatus.ERROR,
    )
    assert result.is_actionable() is False


def test_intent_classification_result_requires_clarification():
    """Test requires_clarification() method."""
    result = IntentClassificationResult(
        original_request="test",
        predicted_intent=IntentCategory.DOCUMENT_QUESTION_ANSWERING,
        confidence=0.3,
        status=ClassificationStatus.CLARIFICATION_REQUIRED,
    )
    assert result.requires_clarification() is True

    result = IntentClassificationResult(
        original_request="test",
        predicted_intent=IntentCategory.DOCUMENT_QUESTION_ANSWERING,
        confidence=0.9,
        status=ClassificationStatus.CONFIDENT,
    )
    assert result.requires_clarification() is False


def test_intent_classification_result_requires_special_handling():
    """Test requires_special_handling() method."""
    for cat in IntentCategory.special():
        result = IntentClassificationResult(
            original_request="test",
            predicted_intent=cat,
            confidence=0.9,
            status=ClassificationStatus.CONFIDENT,
        )
        assert result.requires_special_handling() is True, f"{cat} should require special handling"

    for cat in IntentCategory.supported():
        result = IntentClassificationResult(
            original_request="test",
            predicted_intent=cat,
            confidence=0.9,
            status=ClassificationStatus.CONFIDENT,
        )
        assert result.requires_special_handling() is False, f"{cat} should not require special handling"


def test_intent_classification_result_with_none_intent():
    """Test requires_special_handling with None intent."""
    result = IntentClassificationResult(
        original_request="test",
        predicted_intent=None,
        confidence=0.0,
        status=ClassificationStatus.ERROR,
    )
    assert result.requires_special_handling() is True
