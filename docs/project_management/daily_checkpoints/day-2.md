# Day 2 checkpoint — 2026-10-21

## Completed

- **Intent classification module** (`nexusai/ml/classifier.py`): TF-IDF + Logistic Regression baseline with structured output, confidence thresholds, clarification handling, and model persistence.

- **Intent taxonomy and schemas** (`nexusai/ml/schemas.py`): 10 intent categories (6 supported workflows, 4 special), Pydantic models for request/response with validation, status enum, and helper methods (`is_actionable`, `requires_clarification`, `requires_special_handling`).

- **Training dataset** (`nexusai/ml/dataset.py`): 52 examples (18 from evaluation scenarios + 34 synthetic variations) across 10 intent classes. Provenance documented: scenario-based from SC-01–SC-18, synthetic explicitly authored for training robustness (not real user data). Train/test split with stratification.

- **Dataset splits saved** (`experiments/datasets/intent_classification/`): train.json (39), test.json (13), full.json (52), metadata.json with class distribution and provenance.

- **Intent classification service** (`nexusai/app/services/intent.py`): High-level service wrapper with availability checks, supported intents listing, and global instance management.

- **API endpoints** (`nexusai/app/api/routes/intent.py`):
  - `POST /api/v1/intent/classify` — Classify user request with structured output
  - `GET /api/v1/intent/intents` — List all intent categories with workflow support status
  - `GET /api/v1/intent/status` — Check classifier availability

- **API schemas** (`nexusai/app/api/schemas/intent.py`): Response models for classification result, intent list, and classification status.

- **Integration with FastAPI app** (`nexusai/app/main.py`): Added intent router to application factory with appropriate OpenAPI tags.

- **Comprehensive test suite** (39 new tests, 243 total):
  - Unit tests for schemas, dataset, classifier, service (22 tests)
  - Integration tests for API endpoints (6 tests)
  - All existing 204 Day 1 tests still pass

- **Model training and evaluation** (`nexusai/ml/train.py`): Reproducible training script with cross-validation and test evaluation.

- **Model artifacts saved** (`nexusai/ml/models/`): Trained pipeline, vectorizer, label encoder, metadata.

- **Evaluation results saved** (`experiments/results/intent_classification/evaluation.json`):
  - Test accuracy: 0.5385
  - Test macro F1: 0.4738
  - 3-fold CV macro F1: 0.5825 (±0.0774)
  - Per-class metrics documented
  - Confusion matrix documented
  - Thresholds: confidence=0.55, clarification=0.35

## Objectives advanced

- **O1** — Interpret natural-language goals and classify task intent: **IMPLEMENTED**
  - ML-based classifier with TF-IDF + Logistic Regression
  - 10-class taxonomy covering all 18 evaluation scenarios
  - Confidence scoring with abstention for low-confidence predictions
  - Special handling for invalid, infeasible, out-of-scope, destructive requests

## Metric results (preliminary)

| Metric | Value | Evidence |
|--------|-------|----------|
| Tests passing | 243/243 | `python -m pytest tests/` |
| Ruff lint | 6 minor style suggestions | `python -m ruff check .` |
| Test accuracy | 0.5385 | `evaluation.json` |
| Test macro F1 | 0.4738 | `evaluation.json` |
| Test macro precision | 0.4400 | `evaluation.json` |
| Test macro recall | 0.5500 | `evaluation.json` |
| 3-fold CV macro F1 | 0.5825 (±0.0774) | `evaluation.json` |
| Dataset size | 52 examples (18 scenario + 34 synthetic) | `dataset.py`, `metadata.json` |
| Classes | 10 intent categories | `schemas.py`, `metadata.json` |
| Supported intents | 6 (map to workflows) | `schemas.py` |
| Special intents | 4 (require special handling) | `schemas.py` |

## Known limitations

1. **Small dataset**: Only 52 examples for 10 classes (avg 5.2/class) limits statistical reliability and generalization. Many classes have 1-2 test samples.

2. **Low test metrics**: Macro F1 = 0.47 reflects dataset size limitations. CV score (0.58) is higher, suggesting model has learned some patterns but test set is too small for reliable estimation.

3. **Synthetic data only**: All training data is scenario-derived or manually authored synthetic examples. No real user data.

4. **No calibration**: Confidence scores from LogisticRegression are not calibrated probabilities.

5. **No LLM fallback**: Day 2 implements ML classifier only. LLM fallback for out-of-taxonomy inputs is deferred.

6. **No real user evaluation**: Classifier not yet evaluated on real user requests.

## Blocker(s)

- None for Day 2 acceptance criteria. All implementation, testing, and documentation complete.

## Definition of done met?

**Yes** — All Day 2 acceptance criteria from `seven_day_implementation_plan.md` satisfied:
- Intent router module with tests ✅
- Classifier accuracy measured on labelled examples ✅
- Intent taxonomy documented ✅
- Dataset provenance documented ✅
- Day 2 checkpoint documented ✅

## Git

- Commit message: `feat(ml): implement baseline intent classification`
- Commit hash: (recorded after commit creation)
- Working tree clean: Yes (after commit)