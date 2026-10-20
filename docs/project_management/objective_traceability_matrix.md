# Objective Traceability Matrix

**Project:** NexusAI  
**Document status:** Draft v0.1 — Phase 0 research foundation  
**Date:** 2026-10-20

## 1. Purpose

Every research objective O1–O6 must map to:
- an application component,
- an implementation milestone,
- a test or experiment,
- an evaluation metric, and
- a research document or result.

This matrix is updated throughout development. A row without evidence in every column is incomplete.

## 2. Matrix

| Objective | Application component | Implementation milestone | Test / experiment | Evaluation metric | Research document / result |
|-----------|----------------------|--------------------------|-------------------|-------------------|----------------------------|
| O1 — Interpret natural-language goals; classify task intent | Intent router (classifier + LLM fallback) | Day 2: intent router module with tests | Classifier accuracy on labelled intent examples; out-of-taxonomy fallback behaviour | Intent classification accuracy (component metric) | `research_questions.md` (RQ1.2); `research_methodology.md`; Day-2 checkpoint |
| O2 — Structured task planning with dependencies | Planner (typed plan schema, dependency graph) | Day 3: planner module with schema conformance | Plan schema-conformance scoring on generated plans | Planning quality score | `research_gap.md` (C1); `architecture/system_overview.md`; Day-3 checkpoint |
| O3 — RAG over user-provided documents | RAG module (index, retrieval, citations) | Day 4: RAG module | Evidence support scoring on retrieved passages | Evidence accuracy | `research_questions.md` (RQ1.3); `architecture/system_overview.md`; Day-4 checkpoint |
| O4 — Secure tool execution with validation | Tool registry + Executor (schema validation, approval gate) | Day 5: executor module | Invalid-invocation rate; tool-selection accuracy | Tool-selection accuracy; invalid-invocation rate | `research_gap.md` (C4); `architecture/system_overview.md`; Day-5 checkpoint |
| O5 — Verification, bounded retries, failure handling, replanning | Verifier + Replanner (independent check, bounded budget) | Day 6: verifier + replanner modules | Verification agreement with human labels; recovery within budget | Verification accuracy; recovery effectiveness | `research_gap.md` (C2/C3); `architecture/system_overview.md`; Day-6 checkpoint |
| O6 — Evaluate performance with measurable metrics | Experiment harness + Report generator | Day 7: end-to-end integration + first experiment pass | Full test matrix (conditions A/B/C); ablations | Task completion, planning quality, tool-selection accuracy, verification accuracy, recovery effectiveness, evidence accuracy, execution time | `experimental_design.md`; `evaluation_metrics.md`; Day-7 checkpoint; preliminary analysis for Second Review |

## 3. Update protocol

Whenever a milestone is completed:
1. Update the "Implementation milestone" and "Test / experiment" columns with evidence (file paths, test names, result summary).
2. Add the metric result value (preliminary) to the "Evaluation metric" column.
3. Link the checkpoint report in the "Research document / result" column.
4. Commit the updated matrix with the day's work.

A row is **complete** only when all six columns contain concrete evidence.

---

**Traceability:** This matrix is the single source linking research objectives to code, tests, metrics, and documents. It is reviewed at each daily checkpoint and before the Second Review.