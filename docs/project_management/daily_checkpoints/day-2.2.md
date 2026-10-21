# Day 2.2 checkpoint — 2026-10-21 (Intent Classifier Reliability Improvement)

## Completed

- **Revised intent taxonomy** (`nexusai/ml/schemas.py`): Expanded from 10 to 12 classes with clearer separation:
  - **Supported workflows (7)**: `document_question_answering`, `document_summarisation`, `data_analysis`, `research`, `communication`, `document_extraction`, `document_transformation`
  - **Special handling (5)**: `destructive_operation`, `invalid`, `infeasible`, `out_of_scope`, `channel_unavailable`
  - Added `requires_approval()` method for explicit approval-gated intents
  - Split `document_operation` into `document_extraction` (read-only) and `document_transformation` (write/transform)
  - Added `channel_unavailable` for unsupported communication channels
  - Added `requires_approval()` method for explicit approval-gated intents (destructive operations)

- **Expanded dataset** (`nexusai/ml/dataset.py`): 75 examples (19 scenario-based + 56 synthetic) across 12 intent classes:
  - Added 22 new synthetic examples covering all 12 intent classes
  - Balanced class distribution (3-12 examples per class)
  - Documented provenance for all examples (scenario-based vs synthetic)
  - Added near-duplicate detection (TF-IDF cosine similarity ≥ 0.85)
  - Added group-based splitting by source to prevent leakage

- **Improved classifier** (`nexusai/ml/classifier.py`):
  - Added `ModelType` enum supporting `LOGISTIC_REGRESSION` and `LINEAR_SVC`
  - Optional probability calibration via `CalibratedClassifierCV` (sigmoid/isotonic)
  - Fixed threshold tuning bug: now starts from `min(max_probas)` instead of hardcoded 0.30
  - Automatic `clarification_threshold = 0.5 * confidence_threshold`
  - Graceful calibration fallback when insufficient samples per class
  - Proper model saving/loading for both Pipeline and CalibratedClassifierCV

- **Proper evaluation pipeline** (`nexusai/ml/train.py`):
  - 60/20/20 train/val/test split (stratified, random_state=42)
  - Model comparison: LogisticRegression (calibrated/uncalibrated) vs LinearSVC (calibrated)
  - Cross-validation on training set (3-fold StratifiedKFold)
  - Threshold tuning on validation set (maximizing selective accuracy × coverage)
  - Final model trained on train+val, evaluated on held-out test set
  - Comprehensive metrics: accuracy, macro P/R/F1, per-class metrics, confusion matrix

- **Model comparison results** (75 examples, 12 classes, 45 train / 15 val / 15 test):

  | Model | Val macro F1 | Test macro F1 | CV macro F1 |
  |-------|-------------|---------------|-------------|
  | LogisticRegression (calibrated) | 0.431 | 0.500 | 0.437 ± 0.091 |
  | LinearSVC (calibrated) | 0.379 | 0.514 | 0.430 ± 0.201 |
  | LogisticRegression (uncalibrated) | **0.639** | 0.442 | 0.437 ± 0.091 |

  **Best model**: LogisticRegression (uncalibrated) — selected on validation macro F1 (0.639)
  - Final test (train+val → test): accuracy 0.667, macro F1 0.622
  - Tuned thresholds: confidence=0.55, clarification=0.28

- **Per-class test metrics** (final model, 15 test samples):

  | Class | Precision | Recall | F1 | Support |
  |-------|----------|--------|-----|---------|
  | channel_unavailable | 1.00 | 1.00 | 1.00 | 1 |
  | communication | 1.00 | 1.00 | 1.00 | 1 |
  | data_analysis | 0.00 | 0.00 | 0.00 | 2 |
  | destructive_operation | 0.00 | 0.00 | 0.00 | 1 |
  | document_extraction | 0.33 | 1.00 | 0.50 | 1 |
  | document_question_answering | 0.67 | 1.00 | 0.80 | 2 |
  | document_summarisation | 1.00 | 0.50 | 0.67 | 2 |
  | document_transformation | 1.00 | 1.00 | 1.00 | 1 |
  | infeasible | 0.00 | 0.00 | 0.00 | 1 |
  | invalid | 0.33 | 1.00 | 0.50 | 1 |
  | out_of_scope | 1.00 | 1.00 | 1.00 | 1 |
  | research | 1.00 | 1.00 | 1.00 | 1 |

- **Confidence & safety behaviour**:
  - Tuned thresholds: `confidence_threshold=0.55`, `clarification_threshold=0.28`
  - Three-tier status: `confident` (≥0.55), `low_confidence` (0.275–0.55), `clarification_required` (<0.275)
  - Destructive operations: `requires_approval()` returns True, `is_actionable()` returns False
  - Special intents (invalid, infeasible, out_of_scope, channel_unavailable): non-actionable with abstention reasons

- **Safety separation**:
  - Classifier never authorizes execution; `is_actionable()` and `requires_approval()` are separate from classification
  - Destructive operations require explicit approval via `requires_approval()` check
  - Channel unavailable intents handled as special (non-actionable) with clarification

- **API integration** (`nexusai/app/api/routes/intent.py`):
  - `POST /api/v1/intent/classify` — structured classification with confidence/status
  - `GET /api/v1/intent/intents` — lists all 12 categories with `supported` flag
  - `GET /api/v1/intent/status` — classifier availability check

- **Comprehensive test suite** (246 tests passing):
  - 24 unit tests for schemas, dataset, classifier, service
  - 6 integration tests for API endpoints
  - 246 total tests passing (including all Day 1 regressions)

## Objectives Advanced

- **O1** — Interpret natural-language goals and classify task intent: **IMPLEMENTED**
  - 12-class taxonomy with structured output, confidence scores, and abstention
  - ML-based classifier with calibrated probabilities (optional)
  - Proper threshold tuning on validation data

## Metric Results (Preliminary)

| Metric | Value | Evidence |
|--------|-------|----------|
| Tests passing | 246/246 | `python -m pytest tests/` |
| Ruff lint | 6 style suggestions (all unsafe) | `python -m ruff check .` |
| Val macro F1 (best) | 0.6385 | `evaluation.json` |
| Test macro F1 (final) | 0.6222 | `evaluation.json` |
| Test accuracy | 0.667 | `evaluation.json` |
| Dataset size | 75 examples (19 scenario + 56 synthetic) | `metadata.json` |
| Classes | 12 | `schemas.py` |
| Supported intents | 7 | `schemas.py` |

## Blockers / Open Items

- **Small dataset**: 75 examples for 12 classes (avg 6.25/class) limits statistical reliability
- **Class imbalance**: Some classes have only 3-4 examples total (channel_unavailable: 3, destructive_operation: 4)
- **Low test F1 for several classes**: data_analysis (0.00), destructive_operation (0.00), infeasible (0.00) due to minimal test support
- **No calibration**: Probabilities not calibrated (dataset too small for Platt scaling)
- **No LLM fallback**: ML classifier only; out-of-taxonomy handled by abstention
- **Near-duplicates**: Not formally checked across scenario/synthetic boundary

## Definition of Done Met?

**Partial** — Implementation complete and tested, but evaluation metrics indicate the classifier is not yet reliable enough to serve as a solid baseline for Day 3. The model shows promising results on well-represented classes but fails on under-represented classes (data_analysis, destructive_operation, infeasible all F1=0.00).

**Required before Day 3**:
1. Expand dataset to ≥10 examples per class (target ≥120 total)
2. Add probability calibration (Platt scaling) with validation evaluation
3. Improve per-class F1 to ≥0.70 for all supported intents
6. Verify confidence calibration (reliability diagrams, ECE)

## Git

- Commit: `feat(ml): improve intent classifier reliability`
- Hash: (recorded after commit)
- Working tree: Clean (after commit)

---

**Conclusion**: Day 2.2 reliability improvements complete. The classifier now has a proper evaluation pipeline, model comparison, fixed threshold tuning, and improved taxonomy. However, the fundamental limitation of small dataset size prevents reliable deployment as Day 3 input. Recommend expanding dataset and re-evaluating before Day 3.

**Next step**: Expand dataset to ≥120 examples (10/class), add calibration, re-evaluate, then proceed to Day 3.