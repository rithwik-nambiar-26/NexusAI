"""Tests for intent classifier."""

from __future__ import annotations

import pytest

from nexusai.ml.classifier import IntentClassifier, reset_classifier
from nexusai.ml.schemas import (
    ClassificationStatus,
    IntentClassificationRequest,
)


@pytest.fixture(autouse=True)
def _reset():
    """Reset classifier between tests."""
    reset_classifier()
    yield
    reset_classifier()


def test_classifier_initialization():
    """Test classifier can be initialized."""
    clf = IntentClassifier()
    assert not clf.is_ready()
    assert clf.confidence_threshold == 0.55
    assert clf.clarification_threshold == 0.35


def test_classifier_custom_thresholds():
    """Test classifier with custom thresholds."""
    clf = IntentClassifier(confidence_threshold=0.7, clarification_threshold=0.4)
    assert clf.confidence_threshold == 0.7
    assert clf.clarification_threshold == 0.4


def test_predict_without_model(tmp_path):
    """Test prediction fails gracefully without model."""
    import nexusai.ml.classifier as clf_module

    # Override model paths to use temp directory
    original_model_path = clf_module.MODEL_PATH
    original_vec_path = clf_module.VECTORIZER_PATH
    original_le_path = clf_module.LABEL_ENCODER_PATH
    original_meta_path = clf_module.METADATA_PATH

    clf_module.MODEL_PATH = tmp_path / "test_model.pkl"
    clf_module.VECTORIZER_PATH = tmp_path / "test_vec.pkl"
    clf_module.LABEL_ENCODER_PATH = tmp_path / "test_le.pkl"
    clf_module.METADATA_PATH = tmp_path / "test_meta.json"

    try:
        reset_classifier()
        clf = IntentClassifier()
        # Ensure no model is loaded
        clf._is_fitted = False
        clf.pipeline = None
        clf.label_encoder = None

        req = IntentClassificationRequest(text="Test request")
        result = clf.predict(req)

        assert result.status == ClassificationStatus.ERROR
        assert result.predicted_intent is None
        assert "not trained" in result.abstention_reason.lower()
    finally:
        clf_module.MODEL_PATH = original_model_path
        clf_module.VECTORIZER_PATH = original_vec_path
        clf_module.LABEL_ENCODER_PATH = original_le_path
        clf_module.METADATA_PATH = original_meta_path


def test_predict_empty_input():
    """Test prediction with empty input."""
    clf = IntentClassifier()
    req = IntentClassificationRequest(text="   ")
    result = clf.predict(req)

    assert result.predicted_intent == "invalid"
    assert result.confidence == 1.0
    assert result.status == ClassificationStatus.CONFIDENT


def test_classifier_train_and_predict():
    """Test basic training and prediction."""
    clf = IntentClassifier()

    # Minimal training data
    train_texts = [
        "Summarize this document",
        "What is in the manual?",
        "Analyze the sales data",
        "Research the best tools",
        "Send an email to john",
        "Delete all files",
        "Book a flight to Mars",
    ]
    train_labels = [
        "document_summarisation",
        "document_question_answering",
        "data_analysis",
        "research",
        "communication",
        "destructive_operation",
        "infeasible",
    ]

    metadata = clf.train(train_texts, train_labels)
    assert metadata["n_classes"] == 7
    assert metadata["n_train_samples"] == 7
    assert clf.is_ready()

    # Test prediction
    req = IntentClassificationRequest(text="Summarize the report")
    result = clf.predict(req)
    assert result.predicted_intent == "document_summarisation"
    assert result.confidence > 0


def test_classifier_save_load():
    """Test model save and load."""
    import tempfile
    from pathlib import Path

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

    # Save to temp directory
    with tempfile.TemporaryDirectory() as tmpdir:
        model_path = Path(tmpdir) / "test_model.pkl"
        vec_path = Path(tmpdir) / "test_vec.pkl"
        le_path = Path(tmpdir) / "test_le.pkl"
        meta_path = Path(tmpdir) / "test_meta.json"

        # Monkey-patch paths
        import nexusai.ml.classifier as clf_module
        original_model_path = clf_module.MODEL_PATH
        original_vec_path = clf_module.VECTORIZER_PATH
        original_le_path = clf_module.LABEL_ENCODER_PATH
        original_meta_path = clf_module.METADATA_PATH

        clf_module.MODEL_PATH = model_path
        clf_module.VECTORIZER_PATH = vec_path
        clf_module.LABEL_ENCODER_PATH = le_path
        clf_module.METADATA_PATH = meta_path

        try:
            clf.save()
            assert model_path.exists()
            assert vec_path.exists()
            assert le_path.exists()
            assert meta_path.exists()

            # Load into new classifier
            new_clf = IntentClassifier()
            loaded = new_clf.load()
            assert loaded is True
            assert new_clf.is_ready()
            assert new_clf._classes == clf._classes
        finally:
            clf_module.MODEL_PATH = original_model_path
            clf_module.VECTORIZER_PATH = original_vec_path
            clf_module.LABEL_ENCODER_PATH = original_le_path
            clf_module.METADATA_PATH = original_meta_path


def test_classifier_predict_batch():
    """Test batch prediction."""
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

    requests = [
        "Summarize the report",
        "What does the manual say?",
        "Show me the sales figures",
    ]
    results = clf.predict_batch([IntentClassificationRequest(text=r) for r in requests])

    assert len(results) == 3
    for result in results:
        assert result.predicted_intent is not None
        assert 0 <= result.confidence <= 1
