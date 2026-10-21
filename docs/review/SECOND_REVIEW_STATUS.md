# NexusAI — Second Review Status

**Review:** MSc Data Science Second Review, 23–25 October 2026  
**Status as at:** 2026-10-21, commit `2359145` plus the Day 5.5 integration work  
**Prepared by:** the implementation agent, from the actual repository state

## 1. Executive Summary

NexusAI has a working end-to-end path from a natural-language request to
executed tasks: **classify → plan → execute**, with a real registry, a
real filesystem boundary and a real approval mechanism.

The **comparative research evaluation — the central claim of the project —
is not complete.** The rule-based (condition A), LLM-only (condition B)
and hybrid (condition C) baselines have not been run against the
evaluation matrix. No comparative result, accuracy figure or statistical
claim is made anywhere in this repository.

| Area | State |
|------|-------|
| Intent classification | Implemented and tested |
| Structured planning | Implemented and tested |
| Document intelligence (RAG) | Implemented and tested |
| Controlled tool execution | Implemented and tested |
| Streamlit demonstration interface | Implemented and manually demonstrated |
| Independent verification (O5) | **Not started** — Day 6 |
| Adaptive replanning (O5) | **Not started** — Day 6 |
| Experiment harness (O6) | **Not started** — Day 7 |
| Comparative A/B/C evaluation (O6) | **Not started** — Day 7 |
| Literature verification | **Outstanding** — 26 entries unverified |

## 2. What Is Implemented and Tested

Each item below has automated tests that pass and, where marked, was
exercised manually through the Streamlit interface.

| Component | Location | Tests | Manual |
|-----------|----------|-------|--------|
| FastAPI app, 16 endpoints | `nexusai/app/main.py` | ✅ | ✅ |
| Request-ID middleware, structured logging | `nexusai/app/core/` | ✅ | ✅ |
| Centralised settings and error handling | `nexusai/app/config.py`, `core/exceptions.py` | ✅ | ✅ |
| SQLite persistence (runs and steps) | `nexusai/app/db/` | ✅ | ✅ |
| Intent classifier, 12 classes | `nexusai/ml/classifier.py` | ✅ | ✅ |
| Structured planner, dependency graph | `nexusai/ml/planner/` | ✅ | ✅ |
| Document extraction (PDF, DOCX, TXT, MD) | `nexusai/rag/extractors.py` | ✅ | ✅ |
| Chunking, stable ids, source offsets | `nexusai/rag/chunking.py` | ✅ | ✅ |
| Local embedding and vector index | `nexusai/rag/embeddings.py`, `store.py` | ✅ | ✅ |
| Retrieval, grounded answers, summaries | `nexusai/rag/service.py` | ✅ | ✅ |
| Tool registry and execution engine | `nexusai/app/execution/` | ✅ | ✅ |
| Filesystem access policy | `nexusai/app/security/paths.py` | ✅ | ✅ |
| CSV profiling and aggregation | `nexusai/app/execution/csv_tool.py` | ✅ | ✅ |
| Streamlit demonstration interface | `nexusai/app/ui/` | ✅ | ✅ |

**Test count:** 527 passing, 2 skipped (the symlink tests skip where the
operating system does not permit symlink creation). Ruff reports no
findings.

## 3. What Is Implemented but Not Manually Demonstrated

| Item | Why | How to demonstrate |
|------|-----|--------------------|
| PDF and DOCX extraction | The manual pass used the Markdown and CSV fixtures | Upload a PDF or DOCX on the Document Intelligence page |
| The approval decision endpoint | The registered capabilities are read-only, so no live approval is reachable | Requires a write or send tool, which is Day 5+ work |
| The duplicate-execution guard | Exercised in unit tests, not from the UI | Execute the same plan twice in one session |

## 4. What Is Partially Implemented

| Item | What exists | What is missing |
|------|--------------|------------------|
| Data analysis | The CSV tool profiles a file, reports missing values and descriptive statistics, and aggregates a user-named column | The planner's `data.analyse`, `data.aggregate`, `data.export` and `verify.calculation` steps have no separate implementations; the first step produces the whole result and the rest are skipped |
| Document transformation | `document.transform` and `filesystem.write` are named in the plan | No capability is registered, so those steps are skipped |
| Communication | `communication.draft` and `communication.send` are named in the plan | No capability is registered, so a request to send a message is correctly refused rather than sent |
| Verification | Every plan ends with a verification task | No `verify.content` or `verify.calculation` capability exists yet; those steps are skipped |
| Intent classifier | 12 classes, trained on 75 examples | Per-class F1 is 0.00 for `data_analysis`, `destructive_operation` and `infeasible` on the held-out set |

## 5. What Is Not Implemented

- Independent verification of a result (O5)
- Adaptive replanning after a failure (O5)
- The execution report generator (O5/O6)
- The experiment harness and the condition A/B/C comparison (O6)
- Durable execution history (the report is returned but not replayed)
- A local LLM planning or answering backend (optional by design)
- Any tool that writes, sends or deletes

## 6. Proposed Research Experiments (Not Yet Run)

These are the experiments the research plan calls for. **None has been
run, and no result is claimed.**

| Experiment | Source | State |
|------------|--------|-------|
| Condition A (rule-based) vs B (LLM-only) vs C (hybrid) across 18 scenarios × 5 trials | `docs/research/experimental_design.md` | Not started — needs the Day 7 harness |
| Ablation: RAG on/off within condition C | `docs/research/research_methodology.md` §7 | Not started |
| Ablation: verification on/off within condition C | same | Not started |
| Ablation: retry budget 0/1/2 within condition C | same | Not started |
| Planning-quality (schema conformance) scoring | `docs/research/evaluation_metrics.md` | Not started — the schema exists, the measurement does not |
| Evidence-accuracy scoring of cited passages | same | Not started |
| Human labelling of step outcomes and evidence support | `docs/research/data_collection_plan.md` | Not started |
| Statistical analysis with multiple-comparison correction | `docs/research/research_methodology.md` §7 | Not started |

## 7. Literature Status

**The literature matrix remains unverified.** All 26 entries in
`docs/research/literature_matrix.md` are marked
`REQUIRES EXTERNAL VERIFICATION`, and they must stay marked that way
until each has been checked against its primary source.

This is the single largest outstanding item for criterion 1
(Literature Review and Theoretical Background, 8 marks). The matrix
itself is well structured and maps cleanly onto the project's
contributions, but the *content* of every row is provisional.

## 8. Objective Traceability

| Objective | Description | State | Evidence |
|-----------|-------------|-------|----------|
| **O1** | Interpret natural-language goals and classify task intent | ✅ Implemented and tested | `nexusai/ml/classifier.py`; held-out accuracy 0.667, macro F1 0.622; Day-2, Day-2.1, Day-2.2 checkpoints |
| **O2** | Decompose goals into executable, dependency-aware steps | ✅ Implemented and tested | `nexusai/ml/planner/`; `architecture/planner_design.md`; Day-3 checkpoint |
| **O3** | Retrieve relevant information from user-provided documents | ✅ Implemented and tested | `nexusai/rag/`; `architecture/rag_architecture.md`; Day-4 checkpoint |
| **O4** | Secure tool execution with registered tools and validated inputs | ✅ Implemented and tested | `nexusai/app/execution/`, `app/security/`; `architecture/execution_engine.md`; Day-5 checkpoint |
| **O5** | Verification, bounded retries, failure handling, replanning | ⏳ Partial — bounded retries and failure handling exist; independent verification and replanning do not | `nexusai/app/execution/engine.py` (retries, blocking); Day 6 pending |
| **O6** | Evaluate with measurable metrics | ⏳ Partial — metrics are defined; the harness that produces them is not built | `docs/research/evaluation_metrics.md`; Day 7 pending |

## 9. What to Say About the Research Question

The research question is:

> "Can an AI-driven workflow engine autonomously decompose, execute,
> verify and adapt multi-step everyday tasks using heterogeneous
> real-time information?"

**NexusAI has implemented the decompose and execute halves and
demonstrated them.** The verify and adapt halves are not implemented, so
the question is not yet answered.

The honest position for the review is that the project has a working
mechanism and a defined evaluation design, and the comparative experiment
that would answer the question is scheduled but not complete.

## 10. Risk for the Review

| Risk | Severity | Mitigation |
|------|----------|------------|
| The comparative evaluation is not complete | **High** | Days 6 and 7 remain; the evaluation design, scenario suite and metrics are all in place |
| The literature is unverified | **High** | Verification is independent of Days 6–7 and can proceed in parallel |
| The intent classifier is weak on three classes | Medium | Documented; the classes are the refusal paths, which is where the current behaviour is safest |
| No verification means the system cannot yet detect a wrong answer | Medium | This is exactly what Day 6 adds; the execution report already carries the evidence a verifier needs |
| The dataset is small and synthetic | Medium | Stated in the Day-2.2 checkpoint and in the evaluation documentation |

## 11. Recommended Order of Work Before the Review

1. **Verify the literature** (26 entries) — independent, can start now
2. **Day 6** — independent verifier and bounded replanner
3. **Day 7** — experiment harness and the first A/B/C pass
4. **Rehearse** the 10–12 minute presentation with the live demonstration
5. Update this document, the traceability matrix and the review-readiness
   matrix with the final evidence

---

**Related documents:** `DEMO_SCRIPT.md`, `MANUAL_TEST_CASES.md`,
`IMPLEMENTATION_VS_OBJECTIVES.md`, `KNOWN_LIMITATIONS.md`
