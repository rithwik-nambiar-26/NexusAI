# Review-Readiness Matrix

**Project:** NexusAI  
**Document status:** Draft v0.1 — Phase 0 research foundation  
**Date:** 2026-10-20  
**Review:** Second Review, 23–25 October 2026

## 1. Purpose

Maps each assessment criterion to the evidence required, the current status of that evidence, and the remaining work. **A criterion is never marked complete without actual supporting evidence.** Statuses are limited to: `Not started`, `In progress`, `Evidence ready`, `Complete`.

## 2. Matrix

| # | Criterion | Marks | Required evidence | Current status | Remaining work |
|---|-----------|-------|-------------------|----------------|----------------|
| 1 | Literature Review and Theoretical Background | 8 | `literature_review.md` (synthesis, 5 literature areas); `literature_matrix.md` (structured matrix, ≥ 20 candidate works, all currently **unverified**) | In progress | **Verify every row against primary sources** (title, authors, year, venue, DOI, exact finding with page/section). Add verified works on agent-benchmark pitfalls, LLM tool-injection safety, and capability boundaries. Replace provisional findings with quoted, sourced claims. |
| 2 | Research Design / Project Plan | 6 | `research_questions.md` (RQ1 + 6 sub-questions); `research_hypothesis.md` (H₁/H₀ + construct definitions); `research_methodology.md` (variables, conditions A/B/C, controls, threats to validity); `experimental_design.md` (test matrix, procedure, pre-specified pass criteria, analysis plan); `seven_day_implementation_plan.md`; `objective_traceability_matrix.md` | Evidence ready | Methodology is written but **not yet exercised**. Move to `Complete` once the Phase 1 experiment harness executes one full pass of the test matrix. |
| 3 | Presentation and Clarity | 6 | Consistent terminology across documents; defined technical terms; clear document cross-references; a working end-to-end demo of the system | In progress | Terminology defined in `research_hypothesis.md`; cross-references in place. **Remaining:** finish the end-to-end run producing a real execution report, and rehearse a 10–12 minute presentation with a live demo. |
| 4 | Data Collection Progress | 6 | `data_collection_plan.md`; `experiments/scenarios/` (≥ 15 ground-truth scenario files); `experiments/corpus/` with provenance; `experiments/runs/` (execution traces); `experiments/labels/` (human verification labels) | Not started | **Only the plan exists.** No scenarios, corpus, traces, or labels yet. Scenario authoring is Day 1–2 work; first trace capture follows the Day 7 integration. |
| 5 | Analysis and Interpretation (Preliminary) | 8 | `evaluation_metrics.md`; computed values for all seven dependent variables; condition comparison with CIs, p-values, effect sizes; ablation results; failure-mode coding | Not started | Requires the experiment harness and one full test-matrix pass. **Blocking dependency:** criteria 4 and 5 both depend on Phase 1 implementation. |
| 6 | Consistency with Objectives | 6 | `objectives_and_scope.md` (O1–O6); `objective_traceability_matrix.md` with all six columns evidenced per row; `research_gap.md` (C1–C7) mapped to objectives | Evidence ready | The mapping exists for all six objectives. **Remaining:** fill the "metric result" evidence in each row once preliminary results exist, and confirm each row is complete on all six columns before the review. |

## 3. Summary of status

| Status | Count | Criteria |
|--------|-------|----------|
| Complete | 0 | — |
| Evidence ready | 2 | 2, 6 |
| In progress | 2 | 1, 3 |
| Not started | 2 | 4, 5 |

**Critical path to review readiness:** criteria 4 and 5 (12 of 40 marks) both depend on Phase 1 implementation and a completed experiment run. Literature verification (criterion 1) is independent and can proceed in parallel. The **highest-risk** item is criterion 5, because analysis cannot begin until the harness and traces exist.

## 4. Evidence location

| Evidence | Location | Committed to git? |
|----------|----------|-------------------|
| Research documents | `docs/` | Yes |
| Traceability matrix | `docs/project_management/objective_traceability_matrix.md` | Yes |
| Daily checkpoints | `docs/project_management/daily_checkpoints/` | Yes |
| Scenario definitions | `experiments/scenarios/` | No (gitignored) — *move to a committed `scenarios/` dir if review requires versioned evidence* |
| Corpus | `experiments/corpus/` | No (gitignored) |
| Execution traces | `experiments/runs/` | No (gitignored) |
| Human labels | `experiments/labels/` | No (gitignored) |
| Aggregated results | `experiments/results/` | No (gitignored) |

> **Note for Phase 1:** the gitignore currently excludes all of `experiments/`. If the review panel requires the scenario suite and aggregated results to be versioned as evidence, the gitignore must be narrowed so that `experiments/scenarios/` and `experiments/results/` (aggregated metrics only, no raw user content) are committed. This is a decision to record in `architecture_decisions.md` before Day 7.

## 5. Review readiness rules

- No criterion moves to `Complete` without a linked, inspectable artefact.
- Statuses are updated at every daily checkpoint, not only at the end.
- If an item cannot be completed before 23 October 2026, it is marked with a stated limitation and a mitigation — never silently omitted.

---

**Traceability:** This matrix maps the six review criteria to the research documents, project-management artefacts, and experiment outputs produced by the project.