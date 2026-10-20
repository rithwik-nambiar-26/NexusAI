# Evaluation Metrics

**Project:** NexusAI  
**Document status:** Draft v0.1 — Phase 0 research foundation  
**Date:** 2026-10-20

## 1. Purpose

This document defines the measurable metrics used to evaluate NexusAI and its baselines. Every metric has an operational definition, a data source, and an aggregation rule. Metrics are computed from observed execution traces and independent human verification — never assumed.

## 2. Metric definitions

| Metric | Operational definition | Data source | Aggregation |
|--------|------------------------|-------------|-------------|
| Task completion rate | Fraction of runs reaching a verified successful terminal state | Execution trace + independent verification | Mean over trials per scenario × condition |
| Planning quality | Fraction of plan elements conforming to the typed plan schema (step type, dependencies, preconditions, expected outcome declared) | Generated plan | Mean schema-conformance score per run |
| Tool-selection accuracy | Fraction of steps where the selected tool matches the ground-truth required tool for that sub-goal | Planner output + ground truth | Mean over steps per run |
| Verification accuracy | Agreement between independent verification outcome and human-labelled ground truth for step outcomes | Verifier output + human labels | Mean over steps per run |
| Recovery effectiveness | Fraction of failed steps that reach a successful terminal state within the retry budget | Replanner log | Mean over failed steps per run |
| Evidence accuracy | Fraction of cited evidence passages whose content supports the step's claim (human-labelled) | RAG citations + human labels | Mean over cited passages per run |
| Execution time | Wall-clock time from goal intake to terminal state | Timer | Mean and median per scenario × condition |

## 3. Data requirements

- **Ground truth per scenario:** expected step sequence, required tools, expected outcomes, supporting evidence passages, success criteria, infeasibility flag (for SC-06-style scenarios).
- **Human labels:** independent verification of step outcomes and evidence support, performed by someone not involved in implementing the condition being scored (to reduce rater bias).
- **Execution traces:** complete per-run logs captured automatically (see `experimental_design.md` Section 5).

## 4. Composite reliability score

Reliability (the construct in H₁/H₀) is operationalised as a composite:

`Reliability = w₁·task_completion + w₂·verification_accuracy + w₃·recovery_effectiveness`

Weights are pre-specified before analysis (initial: w₁ = 0.4, w₂ = 0.3, w₃ = 0.3). Sensitivity analysis over weights is reported so the composite conclusion is not weight-dependent.

## 5. Reporting rules

- Report means with 95% confidence intervals for continuous metrics; proportions with confidence intervals for rate metrics.
- Report all trials, not only successful ones.
- Report failures by root cause (planning, tool, retrieval, verification, infeasible).
- Report effect sizes alongside p-values.
- No selective reporting of significant results only.
- Report ablations (RAG on/off, verification on/off, budget 0/1/2) separately from the full condition C result.

## 6. Limitations of the metrics

- Verification accuracy depends on human-label quality; inter-rater agreement should be reported where multiple raters are used.
- Planning quality measures structural conformance, not whether the plan is the *best* possible plan.
- Evidence accuracy measures citation support, not whether the step is otherwise correct.
- Execution time is a trade-off metric: the hybrid system may be slower while more reliable.
- Metrics are specific to the implemented toolset, corpus, and scenarios; they do not generalise beyond those conditions.

---

**Traceability:** Metrics map to research objectives O1–O6 and to dependent variables in `research_methodology.md`; pass criteria are pre-specified in `experimental_design.md`.