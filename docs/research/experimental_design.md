# Experimental Design

**Project:** NexusAI  
**Document status:** Draft v0.1 — Phase 0 research foundation  
**Date:** 2026-10-20

## 1. Purpose

This document operationalises `research_methodology.md` into a concrete, executable experiment plan. It specifies the test matrix, procedure, data capture, and analysis plan so that the same experiment can be re-run and independently verified.

## 2. Hypothesis under test

- **H₁:** The hybrid NexusAI architecture improves reliability of multi-step task automation vs. rule-based and LLM-only baselines.
- **H₀:** No measurable difference in reliability across the dependent variables.

Reliability is operationalised as the composite of task completion rate, verification accuracy, and recovery effectiveness.

## 3. Test matrix

| Factor | Levels |
|--------|--------|
| Condition | A (rule-based), B (LLM-only), C (hybrid NexusAI) |
| Scenario | SC-01 … SC-N (see scenario suite) |
| Repetition | N = 5 trials per scenario × condition |
| RAG ablation (C only) | corpus present / corpus absent |
| Verification ablation (C only) | on / off |
| Replanning budget (C only) | 0 / 1 / 2 retries |

Total runs (minimum, before review): 15 scenarios × 3 conditions × 5 trials = 225 runs, plus ablation runs within condition C.

## 4. Procedure

For each run:

1. Initialise a fresh runtime state (new corpus index, cleared conversation history, cleared tool call log).
2. Present the natural-language goal to the condition's planner.
3. Execute the generated plan step by step:
   - For each step: validate inputs against the tool schema; if state-changing and approval-gated, record the approval decision; execute; capture actual output; run independent verification against the step's declared expected outcome.
   - On verification failure: if retry budget remains, invoke adaptive replanning (revise remaining steps) and re-execute; otherwise mark the step failed and proceed to the terminal state.
4. Record the terminal state: success / partial / failed / refused (infeasible).
5. Capture the full execution trace: goal, intent classification result, plan, per-step inputs/outputs/verification, retrieval citations, retries, approvals, timestamps, final outcome, execution report.
6. Independently verify each step outcome against human-labelled ground truth (for metrics requiring it).

## 5. Data capture per run

| Field | Source |
|-------|--------|
| Run ID, scenario ID, condition, trial number | Experiment harness |
| Natural-language goal | Scenario definition |
| Intent class (predicted) | Intent classifier (conditions B, C) |
| Generated plan (step sequence, dependencies) | Planner |
| Per-step tool selected | Planner |
| Per-step input validated? pass/fail | Tool validator |
| Per-step approval granted? | Approval log (human) |
| Per-step actual output | Tool execution |
| Per-step verification result | Independent verifier |
| Per-step retry count | Replanner |
| Retrieved evidence passages + citations | RAG module |
| Terminal state (success/partial/failed/refused) | Execution harness |
| Execution time (wall clock) | Timer |
| Execution report | Report generator |

## 6. Success / pass criteria (pre-specified)

| Metric | Pass criterion (condition C) |
|--------|------------------------------|
| Task completion rate | C > B and C > A (statistically significant at α = 0.05 after correction) |
| Tool-selection accuracy | C ≥ 0.80 (80% of steps select the correct tool) |
| Verification accuracy | Agreement with human ground truth ≥ 0.85 |
| Recovery effectiveness | ≥ 0.60 of failed steps recovered within budget |
| Evidence accuracy | ≥ 0.80 of cited passages support the step claim |
| Planning quality | ≥ 0.80 structural conformance to plan schema |
| Execution time | Reported; no pass/fail threshold (trade-off metric) |

Note: These pass criteria are **pre-specified targets**, not assumptions of success. The experiment is designed to produce evidence both for and against them.

## 7. Analysis plan

1. Compute each dependent variable per condition (means/proportions, 95% CIs).
2. Compare C vs. B and C vs. A using pre-specified tests (proportion tests for rates; t-test/Mann–Whitney for time).
3. Apply multiple-comparison correction across six dependent variables.
4. Report effect sizes.
5. Run ablations within condition C to attribute contribution to RAG, verification, and replanning.
6. Code all failures by root cause; report failure-mode distribution per condition.
7. Report any condition where C ≤ B or C ≤ A — these are results capable of disproving H₁ and must be reported as such.

## 8. Reproducibility

- Experiment code, scenario definitions, and result logs are committed to the repository.
- Fixed LLM model, temperature, max tokens, and system prompt recorded per condition.
- Hardware and Python environment (3.11) recorded.
- Random seeds recorded per trial.
- Raw traces and metrics are stored under `experiments/` (see `.gitignore` for what must never be committed: secrets/credentials).

## 9. Review checkpoint

A preliminary analysis (criterion: Analysis and Interpretation — Preliminary, 8 marks) is required before the Second Review (23–25 October 2026). At minimum: scenario suite defined, baseline conditions implemented, one full pass of the test matrix completed, and metrics computed for all dependent variables.

---

**Traceability:** Test matrix maps to `research_methodology.md` independent/dependent variables; pass criteria map to `evaluation_metrics.md`; ablations map to `research_gap.md` contributions C1–C7.