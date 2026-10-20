# Research Methodology

**Project:** NexusAI  
**Document status:** Draft v0.1 — Phase 0 research foundation  
**Date:** 2026-10-20

## 1. Research approach

NexusAI uses an **experimental, comparative, mixed-methods** approach within a design-science-inspired frame:

- **Design-science element:** an artefact (the NexusAI workflow engine) is designed and built to address the identified gap (see `research_gap.md`).
- **Experimental element:** controlled, repeated trials compare three conditions under identical scenarios and measurement protocols.
- **Mixed-methods element:** quantitative metrics (task completion, accuracy, timing) are complemented by qualitative inspection of failure modes and execution reports.

The central methodological commitment is that **results must be capable of disproving the hypothesis**. No experiment is designed to guarantee H₁.

## 2. Experimental conditions

| Code | Condition | Description |
|------|-----------|-------------|
| A | Rule-based baseline | Deterministic trigger→action workflows; hand-crafted decomposition; no LLM, no RAG, no classifier, no validation, no replanning beyond fixed retries |
| B | LLM-only baseline | Generative planning and execution in natural language; no intent classifier, no RAG, no input validation, no independent verification, unbounded retry loops |
| C | Hybrid NexusAI | Intent classification + structured plan schema + RAG + schema-validated tool execution + independent verification + bounded retries + adaptive replanning |

Conditions A and B are implemented as faithfully as possible within their constraints so that observed differences are attributable to the hybrid components, not to baseline sabotage.

## 3. Variables

### Independent variables

| Variable | Values / levels |
|----------|-----------------|
| Architecture condition | A (rule-based), B (LLM-only), C (hybrid) |
| Task scenario | From the defined test scenario suite (see Section 5) |
| Document corpus presence | RAG corpus present vs. absent (ablation within condition C) |
| Verification present | Independent verification on vs. off (ablation within condition C) |
| Replanning budget | 0, 1, 2 retries (ablation within condition C) |

### Dependent variables

| Variable | Operational definition | Metric reference |
|----------|------------------------|------------------|
| Task completion | Fraction of scenarios reaching a verified successful terminal state | `evaluation_metrics.md` — task completion rate |
| Planning quality | Structural correctness of the generated plan (step types, dependencies, preconditions match schema) | `evaluation_metrics.md` — planning quality score |
| Tool-selection accuracy | Fraction of steps where the selected tool matches the required tool for the sub-goal | `evaluation_metrics.md` — tool-selection accuracy |
| Verification accuracy | Agreement between independent verification outcome and human-labelled ground truth for step outcomes | `evaluation_metrics.md` — verification accuracy |
| Recovery effectiveness | Fraction of failed steps that reach a successful terminal state within the retry budget | `evaluation_metrics.md` — recovery effectiveness |
| Evidence accuracy | Fraction of cited evidence passages whose content supports the step's claim | `evaluation_metrics.md` — evidence accuracy |
| Execution time | Wall-clock time from goal intake to terminal state | `evaluation_metrics.md` — mean execution time per scenario |

### Controlled conditions

To isolate the effect of condition, the following are held constant across conditions:

- Same test scenario suite and task definitions.
- Same registered tool inventory (same tools, same schemas).
- Same document corpus (for conditions B and C; condition A does not use documents).
- Same LLM(s) where applicable (same model, same temperature, same max tokens, same system prompt except for condition-specific instructions).
- Same evaluation scripts, metrics, and rubrics.
- Same hardware and runtime environment (Python 3.11, local execution; optional local LLM bounded by available hardware).
- Same retry budget where retries are used; identical handling of timeouts and invalid inputs.

## 4. Research design

The design is a **repeated-measures comparative experiment**:

1. **Scenario selection:** define a suite of everyday multi-step scenarios spanning different intent classes and document/tool dependencies (see Section 5).
2. **Dataset construction:** for each scenario, specify ground truth: expected step sequence, required tools, expected outcomes, supporting evidence passages, and success criteria.
3. **Execution:** run each scenario under each condition, with repeated trials (N ≥ 5 per scenario per condition) to average out stochastic LLM behaviour.
4. **Measurement:** compute all dependent variables from execution traces and from independent human verification of outcomes.
5. **Analysis:** compare conditions on each dependent variable using pre-specified statistical tests (Section 7).
6. **Failure analysis:** qualitatively code all failures by root cause (planning error, tool error, retrieval error, verification error, infeasible goal) to inform `analysis_and_interpretation.md`.

## 5. Test scenarios and evaluation datasets

### Test scenario suite (minimum, to be expanded in Phase 1)

Each scenario specifies: natural-language goal, intent class, required tools, required document(s), expected step structure, success criteria, and failure modes to probe.

| ID | Goal (example, not exhaustive) | Intent class | Tools required | Documents required |
|----|-------------------------------|--------------|----------------|--------------------|
| SC-01 | Research a topic and produce a summary with cited sources | research | web_search, summarise | local corpus |
| SC-02 | Compare two products across price and features and recommend one | comparison | web_search, extract | local corpus |
| SC-03 | Draft an email reply incorporating facts from a provided document | communication | draft_email | local document |
| SC-04 | Schedule a recurring reminder across a calendar tool | scheduling | add_event | — |
| SC-05 | Convert and summarise a user-uploaded document | document | convert, summarise | uploaded file |
| SC-06 | Infeasible goal (e.g., book a flight without dates) — must be refused | infeasible | — | — |

Scenarios are expanded in Phase 1 to cover at least 3 intent classes × 2 document conditions × 2 complexity levels, with at least 15 scenarios total before the Second Review.

### Evaluation datasets

- **Scenario suite:** hand-authored scenarios with ground truth (see above). Not fabricated as real user data; explicitly synthetic for controlled evaluation.
- **RAG corpus:** a small, local set of user-provided or synthetic documents used for retrieval; each document's provenance recorded.
- **Intent taxonomy:** closed set of intent classes for the classifier evaluation; labelled examples recorded.

No real personal user data is used without explicit consent and anonymisation; all evaluation data remains local.

## 6. Repeated trials

- Each scenario × condition combination is executed N = 5 times (minimum), with different random seeds / sampling where stochastic.
- Trials are independent: fresh corpus index, fresh conversation state, no carryover between trials.
- Results are reported as means with confidence intervals or as exact counts/proportions, never as single-run anecdotes.

## 7. Statistical analysis approach

- **Primary comparisons:** condition C vs. condition B, and condition C vs. condition A, on each dependent variable.
- **Statistical tests:** selected per metric type — e.g., proportion tests (chi-square or Fisher's exact) for completion/accuracy rates; t-test or Mann–Whitney U for execution time; paired tests where the same scenario is run under multiple conditions.
- **Significance level:** α = 0.05, pre-specified; multiple-comparison correction (e.g., Bonferroni or Holm–Bonferroni) applied across the six dependent variables.
- **Effect sizes:** reported alongside p-values (e.g., Cohen's d, odds ratio) to assess practical significance.
- **Ablations:** within condition C, compare ablation variants (RAG on/off, verification on/off, budget 0/1/2) to attribute contribution to individual components.
- **Reporting:** all trials, means, intervals, p-values, and effect sizes reported in full; selective reporting of only significant results is prohibited.

## 8. Threats to validity

| Threat | Mitigation |
|--------|------------|
| Construct validity | Multiple dependent variables; independent verification rather than self-report |
| Internal validity | Controlled conditions, repeated trials, fixed tool inventory and corpus |
| External validity | Scenarios limited to everyday personal tasks; results not claimed to generalise |
| Conclusion validity | Pre-specified α, multiple-comparison correction, effect sizes, repeated trials |
| Metric gaming | Metrics defined pre-experiment; no post-hoc metric selection |
| LLM stochasticity | Fixed model/parameters where possible; repeated trials and confidence intervals |

## 9. Ethical and reproducibility notes

- No secrets, credentials, or local environment files are committed to the repository (see `.gitignore`).
- All evaluation data is synthetic or user-provided with consent; it remains local.
- Experiment code, scenario definitions, and raw results are versioned alongside the code so results are reproducible from the repository.
- No literature, dataset, or result is fabricated (per non-negotiable constraint).

---

**Traceability:** Variables map to objectives O1–O6; conditions A/B/C ground the hypothesis test in `research_hypothesis.md`; metrics map to `evaluation_metrics.md`; scenarios map to `data_collection_plan.md`.