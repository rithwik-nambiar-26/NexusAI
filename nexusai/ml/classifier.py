"""Intent classification model using TF-IDF + Logistic Regression.

A reproducible, scikit-learn baseline for intent classification.
Follows NexusAI conventions: structured output, confidence handling,
and integration with existing logging/exception infrastructure.
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder

from nexusai.app.core.exceptions import ServiceUnavailableError
from nexusai.app.core.logging import get_logger
from nexusai.ml.schemas import (
    ClassificationStatus,
    IntentCategory,
    IntentClassificationRequest,
    IntentClassificationResult,
)

logger = get_logger("ml.classifier")

# Model artifact paths
MODEL_DIR = Path(__file__).resolve().parent / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

MODEL_PATH = MODEL_DIR / "intent_classifier.pkl"
VECTORIZER_PATH = MODEL_DIR / "tfidf_vectorizer.pkl"
LABEL_ENCODER_PATH = MODEL_DIR / "label_encoder.pkl"
METADATA_PATH = MODEL_DIR / "model_metadata.json"

# Default confidence threshold (tuned on validation data)
DEFAULT_CONFIDENCE_THRESHOLD = 0.55
CLARIFICATION_THRESHOLD = 0.35


class IntentClassifier:
    """TF-IDF + Logistic Regression intent classifier.

    Provides structured classification output with confidence scores,
    abstention for low-confidence predictions, and special handling
    for unsupported/ambiguous requests.
    """

    def __init__(
        self,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        clarification_threshold: float = CLARIFICATION_THRESHOLD,
    ):
        self.confidence_threshold = confidence_threshold
        self.clarification_threshold = clarification_threshold

        self.pipeline: Pipeline | None = None
        self.label_encoder: LabelEncoder | None = None
        self._is_fitted = False
        self._classes: list[str] = []

    def _create_pipeline(self) -> Pipeline:
        """Create the TF-IDF + Logistic Regression pipeline."""
        return Pipeline(
            [
                (
                    "tfidf",
                    TfidfVectorizer(
                        ngram_range=(1, 2),
                        max_features=5000,
                        min_df=1,
                        max_df=0.95,
                        sublinear_tf=True,
                    ),
                ),
                (
                    "clf",
                    LogisticRegression(
                        max_iter=1000,
                        C=1.0,
                        class_weight="balanced",
                        random_state=42,
                        solver="lbfgs",
                    ),
                ),
            ]
        )

    def train(
        self,
        train_texts: list[str],
        train_labels: list[str],
        val_texts: list[str] | None = None,
        val_labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Train the classifier on the provided data.

        Args:
            train_texts: Training texts
            train_labels: Training labels (intent category strings)
            val_texts: Optional validation texts for threshold tuning
            val_labels: Optional validation labels

        Returns:
            Training metadata including validation metrics if provided
        """
        self.label_encoder = LabelEncoder()
        y_train = self.label_encoder.fit_transform(train_labels)
        self._classes = self.label_encoder.classes_.tolist()

        self.pipeline = self._create_pipeline()
        self.pipeline.fit(train_texts, y_train)
        self._is_fitted = True

        metadata = {
            "n_classes": len(self._classes),
            "classes": self._classes,
            "n_train_samples": len(train_texts),
            "confidence_threshold": self.confidence_threshold,
            "clarification_threshold": self.clarification_threshold,
        }

        # Evaluate on validation set if provided
        if val_texts is not None and val_labels is not None:
            val_metrics = self._evaluate(val_texts, val_labels)
            metadata["validation"] = val_metrics

            # Tune confidence threshold on validation set
            self._tune_threshold(val_texts, val_labels)

        logger.info(
            "Intent classifier trained",
            extra={
                "n_classes": len(self._classes),
                "n_train": len(train_texts),
            },
        )

        return metadata

    def _evaluate(self, texts: list[str], labels: list[str]) -> dict[str, Any]:
        """Evaluate model on test data."""
        from sklearn.metrics import (
            accuracy_score,
            classification_report,
            confusion_matrix,
            f1_score,
            precision_score,
            recall_score,
        )

        if not self._is_fitted:
            raise ServiceUnavailableError("Model not trained")

        y_true = self.label_encoder.transform(labels)
        y_pred = self.pipeline.predict(texts)

        accuracy = accuracy_score(y_true, y_pred)
        macro_precision = precision_score(y_true, y_pred, average="macro", zero_division=0)
        macro_recall = recall_score(y_true, y_pred, average="macro", zero_division=0)
        macro_f1 = f1_score(y_true, y_pred, average="macro", zero_division=0)

        # Per-class metrics
        report = classification_report(
            y_true, y_pred, target_names=self._classes, output_dict=True, zero_division=0
        )
        cm = confusion_matrix(y_true, y_pred)

        return {
            "accuracy": accuracy,
            "macro_precision": macro_precision,
            "macro_recall": macro_recall,
            "macro_f1": macro_f1,
            "per_class": {
                cls: {
                    "precision": report[cls]["precision"],
                    "recall": report[cls]["recall"],
                    "f1": report[cls]["f1-score"],
                    "support": int(report[cls]["support"]),
                }
                for cls in self._classes
            },
            "confusion_matrix": cm.tolist(),
            "confusion_matrix_labels": self._classes,
        }

    def _tune_threshold(self, val_texts: list[str], val_labels: list[str]) -> None:
        """Tune confidence threshold on validation data.

        Selects threshold that maximizes selective accuracy while
        maintaining reasonable coverage.
        """
        if not self._is_fitted:
            return

        probas = self.pipeline.predict_proba(val_texts)
        max_probas = np.max(probas, axis=1)
        preds = self.pipeline.predict(val_texts)
        true_labels = self.label_encoder.transform(val_labels)
        correct = preds == true_labels

        # Try thresholds from minimum observed max probability to 0.9
        # (previously started at 0.30, but model max prob can be lower)
        min_threshold = float(max(0.0, max_probas.min() - 0.01))
        max_threshold = min(0.90, max_probas.max() + 0.01)
        if max_threshold <= min_threshold:
            max_threshold = min_threshold + 0.05

        best_threshold = self.confidence_threshold
        best_score = 0.0

        for threshold in np.arange(min_threshold, max_threshold, 0.05):
            confident = max_probas >= threshold
            if confident.sum() == 0:
                continue
            selective_accuracy = correct[confident].mean()
            coverage = confident.mean()

            # Score combines accuracy and coverage (weighted toward accuracy)
            score = selective_accuracy * 0.7 + coverage * 0.3

            if score > best_score:
                best_score = score
                best_threshold = threshold

        self.confidence_threshold = float(best_threshold)
        # Set clarification threshold to half of confidence threshold (rounded to 2 decimals)
        self.clarification_threshold = round(self.confidence_threshold * 0.5, 2)
        logger.info(
            "Confidence threshold tuned",
            extra={"threshold": self.confidence_threshold, "clarification_threshold": self.clarification_threshold, "score": best_score},
        )

    def predict(self, request: IntentClassificationRequest) -> IntentClassificationResult:
        """Classify a single request.

        Returns structured result with confidence, status, and
        appropriate handling for edge cases.
        """
        text = request.text.strip()

        # Handle empty/invalid input
        if not text:
            return IntentClassificationResult(
                original_request=request.text,
                predicted_intent=IntentCategory.INVALID,
                confidence=1.0,
                status=ClassificationStatus.CONFIDENT,
                entities={},
                all_scores={c.value: 0.0 for c in IntentCategory},
            )

        if not self._is_fitted:
            # Try to load model
            self.load()

        if not self._is_fitted:
            return IntentClassificationResult(
                original_request=request.text,
                predicted_intent=None,
                confidence=0.0,
                status=ClassificationStatus.ERROR,
                entities={},
                all_scores={},
                abstention_reason="Model not trained or loaded",
            )

        # Get prediction and probabilities
        probas = self.pipeline.predict_proba([text])[0]
        pred_idx = int(np.argmax(probas))
        confidence = float(probas[pred_idx])
        predicted_label = self.label_encoder.inverse_transform([pred_idx])[0]

        # Build all_scores dict
        all_scores = {
            self.label_encoder.inverse_transform([i])[0]: float(prob)
            for i, prob in enumerate(probas)
        }

        # Determine status based on confidence
        if confidence >= self.confidence_threshold:
            status = ClassificationStatus.CONFIDENT
        elif confidence >= self.clarification_threshold:
            status = ClassificationStatus.LOW_CONFIDENCE
        else:
            status = ClassificationStatus.CLARIFICATION_REQUIRED

        # Map to IntentCategory enum
        try:
            predicted_intent = IntentCategory(predicted_label)
        except ValueError:
            # Unknown label (shouldn't happen with proper training)
            predicted_intent = IntentCategory.INVALID
            status = ClassificationStatus.ERROR

        # Build result
        result = IntentClassificationResult(
            original_request=request.text,
            predicted_intent=predicted_intent,
            confidence=confidence,
            status=status,
            entities={},
            all_scores=all_scores,
        )

        # Add clarification question for low confidence
        if status == ClassificationStatus.CLARIFICATION_REQUIRED:
            result.clarification_question = (
                f"I'm not sure I understand. Are you asking about "
                f"{predicted_label.replace('_', ' ')}? "
                f"Could you rephrase or provide more details?"
            )

        # Add abstention reason for special categories
        if result.requires_special_handling():
            if predicted_intent == IntentCategory.INVALID:
                result.abstention_reason = "Input appears to be empty or malformed."
            elif predicted_intent == IntentCategory.INFEASIBLE:
                result.abstention_reason = "This request appears infeasible with current capabilities."
            elif predicted_intent == IntentCategory.OUT_OF_SCOPE:
                result.abstention_reason = "This request is outside NexusAI's supported scope."
            elif predicted_intent == IntentCategory.DESTRUCTIVE_OPERATION:
                result.abstention_reason = "This is a destructive operation requiring explicit confirmation."

        logger.debug(
            "Intent classification completed",
            extra={
                "intent": predicted_intent.value if predicted_intent else None,
                "confidence": confidence,
                "status": status.value,
            },
        )

        return result

    def predict_batch(self, requests: list[IntentClassificationRequest]) -> list[IntentClassificationResult]:
        """Classify multiple requests."""
        return [self.predict(req) for req in requests]

    def save(self) -> None:
        """Save model artifacts to disk."""
        if not self._is_fitted:
            raise ServiceUnavailableError("Cannot save untrained model")

        MODEL_DIR.mkdir(parents=True, exist_ok=True)

        with open(MODEL_PATH, "wb") as f:
            pickle.dump(self.pipeline, f)

        with open(VECTORIZER_PATH, "wb") as f:
            pickle.dump(self.pipeline.named_steps["tfidf"], f)

        with open(LABEL_ENCODER_PATH, "wb") as f:
            pickle.dump(self.label_encoder, f)

        metadata = {
            "classes": self._classes,
            "n_classes": len(self._classes),
            "confidence_threshold": self.confidence_threshold,
            "clarification_threshold": self.clarification_threshold,
            "sklearn_version": __import__("sklearn").__version__,
        }

        with open(METADATA_PATH, "w") as f:
            json.dump(metadata, f, indent=2)

        logger.info("Model saved", extra={"path": str(MODEL_DIR)})

    def load(self) -> bool:
        """Load model artifacts from disk.

        Returns:
            True if loaded successfully, False otherwise
        """
        try:
            with open(MODEL_PATH, "rb") as f:
                self.pipeline = pickle.load(f)

            with open(LABEL_ENCODER_PATH, "rb") as f:
                self.label_encoder = pickle.load(f)

            with open(METADATA_PATH) as f:
                metadata = json.load(f)
                self.confidence_threshold = metadata.get("confidence_threshold", DEFAULT_CONFIDENCE_THRESHOLD)
                self.clarification_threshold = metadata.get("clarification_threshold", CLARIFICATION_THRESHOLD)
                self._classes = metadata.get("classes", [])

            self._is_fitted = True
            logger.info("Model loaded", extra={"classes": self._classes})
            return True

        except (FileNotFoundError, EOFError, KeyError) as e:
            logger.warning("Failed to load model", extra={"error": str(e)})
            self._is_fitted = False
            return False

    def is_ready(self) -> bool:
        """Check if model is trained/loaded and ready for predictions."""
        return self._is_fitted and self.pipeline is not None


# Global classifier instance (lazy-loaded)
_classifier: IntentClassifier | None = None


def get_classifier() -> IntentClassifier:
    """Get or create the global classifier instance."""
    global _classifier
    if _classifier is None:
        _classifier = IntentClassifier()
        # Try to load existing model
        _classifier.load()
    return _classifier


def reset_classifier() -> None:
    """Reset global classifier (for testing)."""
    global _classifier
    _classifier = None
