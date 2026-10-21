"""Pydantic schemas for intent classification."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class IntentCategory(str, Enum):
    """Supported intent categories for NexusAI workflow routing.

    Taxonomy derived from the 18 evaluation scenarios (SC-01 through SC-18).
    Categories are consolidated from fine-grained scenario intents into
    actionable workflow-routing classes.
    """

    DOCUMENT_QUESTION_ANSWERING = "document_question_answering"
    DOCUMENT_SUMMARISATION = "document_summarisation"
    DATA_ANALYSIS = "data_analysis"
    RESEARCH = "research"
    COMMUNICATION = "communication"
    DOCUMENT_OPERATION = "document_operation"
    DESTRUCTIVE_OPERATION = "destructive_operation"
    INVALID = "invalid"
    INFEASIBLE = "infeasible"
    OUT_OF_SCOPE = "out_of_scope"

    @classmethod
    def supported(cls) -> list[IntentCategory]:
        """Return intents that map to implemented or planned workflows."""
        return [
            cls.DOCUMENT_QUESTION_ANSWERING,
            cls.DOCUMENT_SUMMARISATION,
            cls.DATA_ANALYSIS,
            cls.RESEARCH,
            cls.COMMUNICATION,
            cls.DOCUMENT_OPERATION,
        ]

    @classmethod
    def special(cls) -> list[IntentCategory]:
        """Return intents that require special handling (no workflow)."""
        return [
            cls.DESTRUCTIVE_OPERATION,
            cls.INVALID,
            cls.INFEASIBLE,
            cls.OUT_OF_SCOPE,
        ]


class ClassificationStatus(str, Enum):
    """Status of the classification result."""

    CONFIDENT = "confident"
    LOW_CONFIDENCE = "low_confidence"
    CLARIFICATION_REQUIRED = "clarification_required"
    ABSTAINED = "abstained"
    ERROR = "error"


class IntentClassificationRequest(BaseModel):
    """Input request for intent classification."""

    text: str = Field(..., min_length=1, max_length=2000, description="Natural-language user request")
    context: dict[str, Any] | None = Field(default=None, description="Optional context from previous turns")


class IntentClassificationResult(BaseModel):
    """Structured output of intent classification.

    Designed for consumption by Day 3's planner and orchestrator.
    """

    original_request: str = Field(..., description="Echo of the input text")
    predicted_intent: IntentCategory | None = Field(default=None, description="Predicted intent category")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Model confidence in prediction")
    status: ClassificationStatus = Field(default=ClassificationStatus.ERROR, description="Classification status")
    entities: dict[str, Any] = Field(default_factory=dict, description="Extracted entities/parameters")
    clarification_question: str | None = Field(default=None, description="Question to user if clarification needed")
    abstention_reason: str | None = Field(default=None, description="Reason for abstention if applicable")
    all_scores: dict[str, float] = Field(default_factory=dict, description="Scores for all intent categories")

    def is_actionable(self) -> bool:
        """Return True if the intent maps to a supported workflow."""
        if self.predicted_intent is None:
            return False
        return self.predicted_intent in IntentCategory.supported()

    def requires_clarification(self) -> bool:
        """Return True if the request needs user clarification."""
        return self.status in (ClassificationStatus.CLARIFICATION_REQUIRED, ClassificationStatus.ABSTAINED)

    def requires_special_handling(self) -> bool:
        """Return True if the intent requires special (non-workflow) handling."""
        if self.predicted_intent is None:
            return True
        return self.predicted_intent in IntentCategory.special()
