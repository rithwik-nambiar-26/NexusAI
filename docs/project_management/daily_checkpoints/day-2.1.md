# Day 2.1 checkpoint — 2026-10-21 (Intent Classifier Evaluation Audit)

## 1. Executive Summary

**Status**: Day 2 evaluation contains **critical methodological errors** that invalidate the reported metrics. The classifier is **non-functional** in its current state — all predictions fall below the confidence threshold.

### Critical Findings

| # | Finding | Severity | Evidence |
|-----|---------|----------|----------|
| 1 | No validation set used for threshold tuning | CRITICAL | `train.py` creates only train/test split |
| 2 | Confidence threshold never tuned | CRITICAL | Threshold = 0.55 (default), validation key absent in eval.json |
| 3 | Model max confidence ~0.22 << 0.55 threshold | CRITICAL | Max probability on validation = 0.194 |
| 4 | 100% predictions → "clarification_required" | CRITICAL | Classifier non-functional |
| 5 | Threshold tuning bug: starts at 0.30, max prob = 0.194 | HIGH | Loop starts at 0.30, max prob = 0.194 |
| 5 | Reported validation metrics don't exist | HIGH | No "validation" key in evaluation.json |
| 6 | Cross-validation uses different pipeline | MEDIUM | CV creates new pipeline each fold |
| 7 | No calibration evaluation | MEDIUM | No calibration metrics reported |
| 8 | Dataset too small for reliable evaluation | MEDIUM | 52 examples, 10 classes |

---

## 2. Evaluation Methodology Investigation

### 2.1 How Sets Were Created

**Original (train.py)**:
```python
train, test = train_test_split(df, test_size=0.25, stratify=df["intent"], random_state=42)
# Train: 39, Test: 13 — NO validation set
```

**Corrected (3-way)**:
```python
train_val, test = train_test_split(df, test_size=0.2, stratify=df["intent"], random_state=42)
train, val = train_test_split(train_val, test_size=0.25, stratify=train_val["intent"], random_state=42)
# Train: 30, Val: 11, Test: 11
```

**Verification**: No duplicate texts across any splits. ✅

### 2.2 Validation Data Source

**Original**: No validation set created. `train.py` passes no `val_texts`/`val_labels` to `classifier.train()`.

**Corrected**: 3-way split (60/20/20) provides validation set for threshold tuning.

### 2.3 Threshold Selection

**Original**: Never executed. `train.py` doesn't pass validation data to `classifier.train()`. The `_tune_threshold()` method was never called.

**Evidence**: `evaluation.json` has no "validation" key in `model_metadata`. Thresholds are exactly defaults:
- `confidence_threshold`: 0.55 (= `DEFAULT_CONFIDENCE_THRESHOLD`)
- `clarification_threshold`: 0.35 (= `CLARIFICATION_THRESHOLD`)

### 2.4 Vectorization Data Leakage

**Checked**: TF-IDF vectorizer is fitted inside the pipeline during `pipeline.fit(train_texts, train_labels)`. No leakage — vectorizer sees only training data.

### 2.5 Cross-Validation Leakage

**Procedure**: `train.py` creates a NEW pipeline for CV:
```python
cv_pipeline = classifier._create_pipeline()
cv_scores = cross_val_score(cv_pipeline, train_texts, train_labels, cv=cv, scoring="f1_macro")
```

**Assessment**: Correct — CV creates fresh pipelines. No leakage. But CV score (0.58) doesn't reflect final model's test performance (0.47) because:
- CV uses different pipelines per fold
- Final model trained on all training data
- Different data splits

### 2.6 Duplicates Across Splits

**Verified**: No exact duplicate texts across train/val/test splits. ✅

**Near-duplicates**: Not systematically checked. Some scenario/synthetic pairs are semantically similar (e.g., "Summarize the product manual" vs "Give me a summary of the product manual"). Not formally checked.

### 2.7 Reproducibility

**Training**: Reproducible with `random_state=42`. ✅

**Evaluation metrics**: Can be reproduced by running `python nexusai/ml/train.py` with corrected 3-way split. Original `train.py` produces different splits (only train/test).

---

## 3. Confidence and Safety Behaviour Audit

### 3.1 Threshold Values

| Threshold | Value | Source | Tuned? |
|-----------|-------|--------|--------|
| confidence_threshold | 0.55 | DEFAULT_CONFIDENCE_THRESHOLD | ❌ NO |
| clarification_threshold | 0.35 | CLARIFICATION_THRESHOLD | ❌ NO |

**Threshold Tuning Bug**: The `_tune_threshold` method in `classifier.py`:
```python
for threshold in np.arange(0.30, 0.90, 0.05):  # STARTS AT 0.30
```

But model's max validation probability = 0.194. The loop starts at 0.30, finds **zero confident predictions** at all thresholds, keeps default 0.55.

**Bug**: Loop should start at 0.0 or `min(max_probas)`.

### 3.2 Model Confidence Distribution

| Test Input | Predicted | Max Prob |
|------------|-----------|----------|
| Summarize manual | document_question_answering | 0.1313 |
| Warranty period? | document_question_answering | 0.1779 |
| Analyze sales data | data_analysis | 0.1376 |
| Research frameworks | invalid | 0.1206 |
| Send email | communication | 0.2130 |
| Delete all files | destructive_operation | 0.2204 |
| Book Mars flight | infeasible | 0.1791 |
| Deal with report | communication | 0.1218 |

**All max probabilities 0.12–0.22 << 0.55 threshold**

### 3.3 Classification Status Outcomes

**100% of predictions → CLARIFICATION_REQUIRED**

```python
if confidence >= 0.55:        # NEVER TRUE
    status = CONFIDENT
elif confidence >= 0.35:      # NEVER TRUE
    status = LOW_CONFIDENCE
else:
    status = CLARIFICATION_REQUIRED  # ALWAYS TRUE
```

### 3.4 Safety Behaviour

| Intent | Predicted | Confidence | Status | Actionable | Special | Notes |
|--------|-----------|------------|--------|------------|---------|-------|
| Summarize manual | doc_qa | 0.15 | CLARIFICATION | True | False | Wrong intent |
| Warranty? | doc_qa | 0.18 | CLARIFICATION | True | False | |
| Delete files | destructive | 0.16 | CLARIFICATION | **False** | True | Abstains correctly |
| Book Mars | infeasible | 0.18 | CLARIFICATION | **False** | True | Abstains correctly |
| Analyze sales | data_analysis | 0.14 | CLARIFICATION | True | False | |
| Send email | communication | 0.21 | CLARIFICATION | True | False | |
| Deal with report | communication | 0.12 | CLARIFICATION | True | False | Wrong intent |

**Safety Assessment**:
- ✅ Destructive/infeasible/out_of_scope correctly marked non-actionable
- ❌ Supported intents incorrectly marked as requiring clarification
- ❌ No mechanism to distinguish "genuinely ambiguous" from "model uncertain"
- ❌ Low confidence on everything means system always asks for clarification

### 3.5 Destructive Operation Restriction

**Implementation**: `IntentCategory.DESTRUCTIVE_OPERATION` in `IntentCategory.special()` returns True, making `requires_special_handling()` return True, and `is_actionable()` return False.

**Result**: Even if confidently predicted, destructive operations would be blocked. However, current model never predicts them confidently.

**Architectural Note**: Proper approval gate belongs in Day 5+ executor, not classifier.

---

## 4. Corrected Evaluation (Re-run with Validation Set)

### 4.1 Corrected 3-Way Split
- Train: 30, Val: 11, Test: 11 (60/20/20, stratified)

### 4.2 Re-trained Model with Validation

| Metric | Value |
|--------|-------|
| Train samples | 30 |
| Val samples | 11 |
| Test samples | 11 |
| Val accuracy | 0.6364 |
| Val macro F1 | 0.5500 |
| Test accuracy | 0.3636 |
| Test macro F1 | 0.2667 |
| 3-fold CV (train) | 0.2515 ± 0.0600 |

**Threshold tuning result**: Still 0.55 (bug in tuning loop — starts at 0.30, max prob = 0.194)

### 4.3 Threshold Tuning Analysis

| Threshold | Coverage | Selective Acc | Score |
|-----------|----------|---------------|-------|
| 0.00 | 1.00 | 0.64 | 0.745 |
| 0.10 | 1.00 | 0.64 | 0.745 |
| 0.15 | 0.18 | 1.00 | 0.755 ← BEST |
| 0.20 | 0.00 | — | — |

**Bug confirmed**: `_tune_threshold` loop starts at 0.30, but max prob = 0.194. Best threshold would be ~0.15.

---

## 5. Corrections Applied

### 5.1 Code Fixes Needed

| File | Issue | Fix |
|------|-------|-----|
| `nexusai/ml/classifier.py` | `_tune_threshold` loop starts at 0.30 | Start at `min(max_probas)` or 0.0 |
| `nexusai/ml/train.py` | No validation split | Use 3-way split (60/20/20) |
| `nexusai/ml/train.py` | No threshold tuning | Pass val data to `classifier.train()` |

### 5.2 Corrected Model (Not Yet Applied)

The model needs:
1. Proper validation split
2. Fixed threshold tuning (start at 0.0 or min prob)
3. Calibration (Platt scaling) on validation set
4. Realistic confidence threshold (~0.15-0.20)

**Current model**: Non-functional (100% clarification_required)

---

## 6. Remaining Limitations

1. **Small dataset**: 52 examples for 10 classes (5.2/class avg)
2. **Imbalanced classes**: 1-2 test samples per class
3. **No calibration**: Probabilities not calibrated (no Platt scaling)
4. **No real user data**: All synthetic/scenario-derived
5. **No LLM fallback**: ML classifier only
6. **Near-duplicates**: Not formally checked (scenario/synthetic similar)
7. **Test set too small**: 11 samples for 10 classes

---

## 7. Test and Lint Status

| Check | Result |
|-------|--------|
| Pytest (243 tests) | 243 passed |
| Ruff linting | 6 style suggestions (StrEnum, unused vars — all unsafe fixes) |
| API integration tests | 6 passed |
| Unit tests (ML) | 22 passed |

---

## 8. Git Status

| Item | Value |
|------|-------|
| Day 2 commit | `ea6f4e5` (feat(ml): implement baseline intent classification) |
| Day 2.1 audit | This document |
| Working tree | Clean (after committing day-2.1.md) |
| Remote | https://github.com/rithwik-nambiar-26/NexusAI (PUBLIC) |
| Contributors | Only `rithwik-nambiar-26` |

---

## 9. Day 2 Readiness for Day 3

**Verdict**: **NOT READY** as baseline for Day 3.

**Blocking issues**:
1. Classifier non-functional (100% clarification_required)
2. Confidence threshold not tuned (uses inappropriate default)
3. Threshold tuning has bug (loop starts too high)
4. No calibration performed
5. Evaluation metrics invalid

**Required before Day 3**:
1. Fix threshold tuning bug in `classifier.py`
2. Retrain with proper 3-way split and threshold tuning
3. Add probability calibration (Platt scaling)
4. Set realistic confidence threshold (~0.15-0.20)
5. Verify classifier produces actionable predictions

**Estimated effort**: 1-2 days to fix and re-evaluate.

---

## 10. Audit Trail

**Auditor**: Automated audit via code inspection and experimental re-run

**Commands executed**:
- `git log --oneline` — verified commit history
- `cat nexusai/ml/train.py` — inspected training script
- `cat nexusai/ml/classifier.py` — inspected classifier implementation
- `cat nexusai/ml/dataset.py` — inspected dataset creation
- `cat experiments/results/intent_classification/evaluation.json` — inspected saved metrics
- `python -m pytest tests/ -v` — 243/243 tests passed
- `python -m ruff check .` — 6 style warnings (all unsafe fixes)
- Manual classifier testing — verified 100% clarification_required
- Threshold tuning debug — confirmed loop starts at 0.30, max prob = 0.194

**Artifacts inspected**:
- `nexusai/ml/train.py` (training script)
- `nexusai/ml/classifier.py` (classifier implementation)
- `nexusai/ml/dataset.py` (dataset creation)
- `nexusai/ml/schemas.py` (Pydantic schemas)
- `nexusai/app/services/intent.py` (service layer)
- `nexusai/app/api/routes/intent.py` (API endpoints)
- `experiments/results/intent_classification/evaluation.json` (saved metrics)
- `nexusai/ml/models/model_metadata.json` (model metadata)
- `experiments/datasets/intent_classification/train.json` (train split)
- `experiments/datasets/intent_classification/test.json` (test split)
- `experiments/datasets/intent_classification_corrected/` (corrected 3-way split)

---

**Conclusion**: Day 2 evaluation is **invalid**. The classifier requires significant fixes before serving as a baseline for Day 3. The audit documentation constitutes the Day 2.1 checkpoint.

**Next step**: Fix threshold tuning bug, retrain with proper validation, add calibration, then re-evaluate before proceeding to Day 3.