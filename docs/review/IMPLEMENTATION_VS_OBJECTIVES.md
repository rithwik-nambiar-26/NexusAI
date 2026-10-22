# NexusAI — Implementation vs Research Objectives

**Project:** NexusAI  
**Review:** MSc Data Science Second Review, 23–25 October 2026  
**Date:** 2026-10-22  
**Basis:** the actual repository at commit `0caad0f` — Days 1–5, the
Day 5.5 Streamlit interface, the intent-confirmation flow and the
reminder capability

## 1. Objective-by-Objective

### O1 — Interpret natural-language goals and classify task intent

**Status: implemented and tested**

| Aspect | Evidence |
|--------|----------|
| Classifier | `nexusai/ml/classifier.py` — TF-IDF + Logistic Regression, optional sigmoid calibration |
| Taxonomy | 13 classes in `nexusai/ml/schemas.py`; 8 workflow-mapped, 5 special-handling. The classifier itself covers 12 — the `reminder` category was added with the capability and the training set predates it |
| Evaluation | Held-out test accuracy 0.667, macro F1 0.622; CV macro F1 0.437 ± 0.091 |
| Model comparison | LogisticRegression (calibrated / uncalibrated) vs LinearSVC, selected on validation |
| Threshold selection | Tuned on the validation split only |
| Integration | `POST /api/v1/intent/classify`; consumed by the planner and the UI |
| Confirmation flow | `nexusai/app/ui/pages/task_automation.py` — ranked candidates with their scores; the user's choice is planned with `source="explicit"` |
| Tests | `tests/unit/ml/test_classifier.py`, `test_schemas.py`, `test_dataset.py`, `tests/integration/test_intent_confirmation.py` |

**Not yet done:** the classifier is experimental. Per-class F1 is 0.00 for
`data_analysis`, `destructive_operation` and `infeasible` on the held-out
set. Its output is treated as a *proposal* throughout the system, never
as ground truth — the planner records the intent's source, and the
executor's safety policy does not depend on the classifier's confidence.

**A defect has been found and deliberately not fixed.** The model-selection
step in `nexusai/ml/train.py` decides whether to calibrate with
`"calibrated" in best_name.lower()`, and the winning variant is
`LogisticRegression (uncalibrated)` — so the substring test is true and
the shipped model is calibrated even though calibration lost on
validation (0.4306 against 0.6385 macro F1). Sigmoid calibration
compresses the predicted probabilities, which is why genuine document
requests score around 0.24–0.45. Fixing the selection changes the model
and every reported metric, so it belongs to the research checkpoint
rather than to a capability change. See `KNOWN_LIMITATIONS.md` §1.4.

---

### O2 — Decompose goals into executable, dependency-aware steps

**Status: implemented and tested**

| Aspect | Evidence |
|--------|----------|
| Plan schema | `nexusai/ml/planner/schemas.py` — `Plan`, `Task`, `TaskParameter`, `TaskType`, `TaskStatus` |
| Decomposition | One registered template per supported intent in `nexusai/ml/planner/service.py` |
| Dependency graph | `nexusai/ml/planner/dependencies.py` — NetworkX, cycle detection, topological order, parallel levels |
| Validation | Duplicate ids, missing references, self-dependencies, cycles, unsupported task types |
| Integration | `POST /api/v1/planner/plan`; the executor consumes the plan |
| Tests | `tests/unit/ml/test_planner_schemas.py`, `test_planner_dependencies.py`, `test_planner_service.py` |
| Documentation | `docs/architecture/planner_design.md` |

**Not yet done:** `planning quality` — the structural-conformance score
defined in `docs/research/evaluation_metrics.md` — is not yet *measured*.
The schema and the validation rules exist; the measurement harness does
not. It is Day 7 work.

---

### O3 — Retrieve relevant information from user-provided documents

**Status: implemented and tested**

| Aspect | Evidence |
|--------|----------|
| Extraction | `nexusai/rag/extractors.py` — PDF (PyMuPDF), DOCX (python-docx), TXT, Markdown |
| Chunking | `nexusai/rag/chunking.py` — normalisation, paragraph packing, stable content-addressed ids, preserved source offsets |
| Embedding | `nexusai/rag/embeddings.py` — deterministic hashing embedder (default) and a local Sentence Transformers embedder |
| Index | `nexusai/rag/store.py` — numpy vector store, metadata filters applied before scoring |
| Retrieval | `nexusai/rag/service.py` — cosine similarity, IDF-weighted sentence selection |
| Grounding | Answers and summaries carry `EvidenceSpan` objects with document, page, heading and chunk id |
| Insufficient evidence | An explicit status with a stated reason and no answer text |
| Tests | `tests/unit/rag/` (5 files), `tests/integration/test_api_documents.py` |
| Documentation | `docs/architecture/rag_architecture.md` |

**Not yet done:** `evidence accuracy` — whether a cited passage actually
supports the claim — is defined in `evaluation_metrics.md` but not
measured. It needs human labelling and the Day 7 harness.

---

### O4 — Secure tool execution with registered tools and validated inputs

**Status: implemented and tested**

| Aspect | Evidence |
|--------|----------|
| Registry | `nexusai/app/execution/registry.py` — frozen `ToolDefinition`, explicit registration only, duplicate rejection, input and output schema validation |
| Engine | `nexusai/app/execution/engine.py` — dependency ordering, failure propagation, timeouts, bounded idempotent retries, structured error categories, duplicate-execution guard |
| Approval | Enforced by the executor, bound to a SHA-256 fingerprint of the task's validated inputs; changed inputs invalidate the approval |
| Safety | Destructive tools are skipped outright; no capability is registered that sends or deletes |
| Filesystem boundary | `nexusai/app/security/paths.py` — canonical resolution, containment check, traversal and symlink-escape refusal, shared by ingestion and execution |
| CSV capability | `nexusai/app/execution/csv_tool.py` — read-only profiling and aggregation |
| Reminder capability | `nexusai/app/execution/reminder_tool.py` — the first write-capable tool. `reminder.create` and `reminder.cancel` are `sensitive` and require approval; `reminder.list` is `safe`. The due time is parsed, and an ambiguous time is reported rather than guessed |
| Scheduler | `nexusai/app/services/reminder_scheduler.py` — an in-process daemon thread. No operating-system job is registered and no external command is run. A reminder due while NexusAI is stopped is recorded as *missed*, never as delivered |
| Integration | `POST /api/v1/execution/execute`, `/approve`; `GET /tools`, `/status` |
| Tests | `tests/unit/execution/` (3 files), `tests/unit/security/test_paths.py`, `tests/integration/test_api_execution.py`, `tests/integration/test_reminders.py` |
| Documentation | `docs/architecture/execution_engine.md`, `docs/review/KNOWN_LIMITATIONS.md` §2.4 |

**Not yet done:** `tool-selection accuracy` and `invalid-invocation rate`
are defined but not measured. The execution report carries the data they
need; the harness that aggregates it is Day 7.

---

### O5 — Execution verification, bounded retries, failure handling, adaptive replanning

**Status: partially implemented**

| Component | State | Evidence |
|-----------|-------|----------|
| Bounded retries | ✅ Implemented | `RetryPolicy` in `registry.py`; only idempotent tools are retried; `max_attempts` and `backoff_seconds` |
| Failure handling | ✅ Implemented | Failed tasks block their dependents; error categories in `ToolErrorCategory` |
| Independent verification | ❌ **Not implemented** | Every plan ends with a `verify.*` task, but no such capability is registered. The verifier must be separate from the planner — that is the point of the design. |
| Adaptive replanning | ❌ **Not implemented** | The planner is invoked once per request. Replanning after a failure needs the Day 6 replanner and a way to clear the duplicate-execution guard for a revised task. |

**How it will be closed (Day 6):** register `verify.content` and
`verify.calculation` as capabilities that check a task's output against
its declared criterion — as a component separate from the planner. The
execution report already carries each task's validated output and the
error that stopped it, which is what a verifier needs.

---

### O6 — Evaluate with measurable metrics

**Status: partially implemented**

| Component | State | Evidence |
|-----------|-------|----------|
| Metric definitions | ✅ Complete | `docs/research/evaluation_metrics.md` — seven metrics with operational definitions, data sources and aggregation rules |
| Composite reliability score | ✅ Defined | Weights w₁=0.4, w₂=0.3, w₃=0.3, with sensitivity analysis required |
| Test matrix | ✅ Defined | `docs/research/experimental_design.md` — 18 scenarios × 3 conditions × 5 trials |
| Scenario suite | ✅ Implemented | 18 scenario files in `experiments/scenarios/`, machine-validated by `tests/unit/test_scenarios.py` |
| Intent-classification metric | ✅ Measured | Held-out accuracy 0.667, macro F1 0.622 (`experiments/results/intent_classification/evaluation.json`) |
| Planning-quality metric | ❌ Not measured | Schema and rules exist; conformance scoring does not |
| Evidence-accuracy metric | ❌ Not measured | Requires human labelling plus the harness |
| Experiment harness | ❌ Not implemented | Needed to run conditions A/B/C |
| Conditions A and B | ❌ Not implemented | The rule-based and LLM-only baselines do not exist yet |
| Statistical analysis | ❌ Not implemented | Significance tests, multiple-comparison correction, effect sizes |

**This is the largest outstanding item for the review.** The
*comparative* evaluation — which is the substance of the research
question — has not been run. The design, the scenarios, the metrics and
the rubric are all in place; the execution of the experiment is not.

---

## 2. Summary Matrix

| Objective | Implemented | Tested | Manually demonstrated | Metric measured |
|-----------|-------------|--------|----------------------|-----------------|
| O1 | ✅ | ✅ | ✅ | ✅ |
| O2 | ✅ | ✅ | ✅ | ❌ |
| O3 | ✅ | ✅ | ✅ | ❌ |
| O4 | ✅ | ✅ | ✅ | ❌ |
| O5 | ⚠️ partial | ✅ (retries, failure handling) | ✅ (blocking behaviour) | ❌ |
| O6 | ⚠️ partial (definitions, scenarios) | ✅ (scenario validation) | ❌ | ❌ |

## 3. What the Demonstration Actually Shows

| Claim the system supports | Where it is shown |
|----------------------------|-------------------|
| A request is classified with a stated confidence | Task Automation, step 2 |
| A request becomes a typed plan with dependencies and an execution order | Task Automation, step 3 |
| The plan names the capabilities each task needs | Task Automation, task table |
| Only registered capabilities run; others are skipped | System status, capabilities table |
| Output is grounded in cited source text | Document Intelligence, answer step |
| Absent evidence produces an explicit refusal | Document Intelligence, insufficient-evidence step |
| Destructive requests produce no plan at all | Task Automation, refusal demo |
| Sends are not performed | Task Automation, refusal demo |
| Files outside the allowed roots cannot be read | Security checks in the test cases |
| A repeated execution does not repeat the work | Task Automation, execute twice |

## 4. What the Demonstration Does Not Show

- Any comparison against a rule-based or LLM-only baseline
- Any independent verification of an answer
- Any adaptive recovery from a failure
- Any statistical result, confidence interval or effect size
- Any literature claim that is not yet verified against a primary source

## 5. Position of the Research Question

> "Can an AI-driven workflow engine autonomously decompose, execute,
> verify and adapt multi-step everyday tasks using heterogeneous
> real-time information?"

**Decompose:** implemented and demonstrated.
**Execute:** implemented and demonstrated, with a registry, a filesystem
boundary and an approval mechanism.
**Verify:** not implemented.
**Adapt:** not implemented.
**Heterogeneous real-time information:** partially — local documents are
handled; web sources are not yet wired to a capability.

**The question is not yet answered.** The project has a working
mechanism and a complete evaluation design. The comparative experiment
that would answer the question is scheduled and instrumented, but not
run.
