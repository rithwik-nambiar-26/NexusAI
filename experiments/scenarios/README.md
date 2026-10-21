# Experimental Scenario Suite

**Project:** NexusAI  
**Status:** Day 1 — initial suite (18 scenarios)  
**Last updated:** 2026-10-20

## 1. Purpose

This directory holds the version-controlled scenario definitions used by the
comparative evaluation described in `docs/research/experimental_design.md`.
Each scenario is a single JSON file so that it can be reviewed, diffed and
cited independently.

The suite exists to compare three experimental conditions under identical
inputs:

| Code | Condition | Definition |
|------|-----------|------------|
| A | Rule-based baseline | Deterministic trigger→action workflows; no LLM, no RAG, no classifier, no validation, no replanning |
| B | LLM-only baseline | Generative planning and execution; no classifier, no RAG, no input validation, no independent verification, unbounded retries |
| C | Hybrid NexusAI | Intent classifier + structured plan + RAG + schema-validated tools + independent verification + bounded retries + adaptive replanning |

## 2. Design principles

These principles exist to keep the evaluation capable of **disproving** the
hypothesis (H₁) rather than merely demonstrating it.

1. **No scenario guarantees the hybrid system wins.** Every scenario carries an
   `adversarial_notes` field stating how the hybrid architecture could fail
   it, and where a baseline may legitimately outperform it.
2. **Correct refusals are scored as correct behaviour.** Scenarios whose
   `expected_outcome` is `refused` or `failed` treat reaching that state as a
   success for the run, not as a task-completion failure.
3. **Not-applicable metrics are null, not zero.** A scenario with no injected
   fault records `recovery_effectiveness` as `null`. Recording it as `0` would
   penalise systems for a failure that was never injected.
4. **Scenarios cover both success and failure paths**, so a system cannot look
   good by only being measured on the easy cases.
5. **Ground truth is stored with the scenario** where it is computable
   (`ground_truth` field), so evaluation does not depend on an unrecorded
   human judgement.

## 3. File format

| Field | Purpose |
|-------|---------|
| `scenario_id` | Stable identifier (`SC-NN`); never reused. |
| `name` | Human-readable title. |
| `category` | Coverage category (see §4). |
| `difficulty` | `low` / `medium` / `hard` — author's prior assessment, not a measured value. |
| `research_objectives` | Objectives O1–O6 the scenario exercises. |
| `research_questions` | Sub-questions RQ1.1–RQ1.6 the scenario informs. |
| `user_input` | The exact natural-language input given to the condition. |
| `expected_intent` | The intent the system should assign. |
| `expected_workflow` | One-line description of the intended workflow shape. |
| `expected_plan` | Step-count bounds, required step types, dependency requirement. |
| `required_tools` | Tools the scenario expects to be used. |
| `required_documents` | Corpus documents the scenario needs. |
| `expected_outcome` | Terminal state: `success` / `failed` / `refused`. |
| `ground_truth` | Computable expected values, where applicable. |
| `fault_injection` | Tool fault to inject (mode + description), where applicable. |
| `approval_policy` | Approval requirement, where applicable. |
| `expected_output_criteria` | Checkable statements about the produced output. |
| `failure_conditions` | Concrete conditions that count as a failure for this scenario. |
| `evaluation_criteria` | Per-metric operational criteria for this scenario. |
| `adversarial_notes` | How the hybrid design can fail here. **Required.** |

## 4. Coverage matrix

| # | Scenario | Category | Objectives | Difficulty | Fault injected |
|---|----------|----------|------------|------------|----------------|
| SC-01 | Summarise a single local document | simple_task | O1, O2, O3 | low | — |
| SC-02 | Research, compare and recommend a product | multi_step | O2, O3, O5, O6 | medium | — |
| SC-03 | Ordered draft-then-send workflow | dependency_ordering | O2, O4, O5 | medium | — |
| SC-04 | Answer a question grounded in a document | document_grounded | O3, O5, O6 | medium | — |
| SC-05 | Question whose answer is not in the corpus | insufficient_evidence | O3, O5, O6 | medium | — |
| SC-06 | Tabular analysis request | data_analysis | O2, O3, O6 | medium | — |
| SC-07 | Invalid or malformed input | invalid_input | O1, O4, O5 | low | — |
| SC-08 | Request requiring an unregistered tool | unknown_tool | O1, O4, O5 | medium | — |
| SC-09 | Tool raises a runtime error | tool_execution_failure | O4, O5, O6 | medium | error once |
| SC-10 | Transient failure that succeeds on retry | transient_failure | O4, O5, O6 | medium | timeout once |
| SC-11 | Permanent failure with no alternative | permanent_failure | O4, O5, O6 | hard | always error |
| SC-12 | Tool returns a well-formed but incorrect result | verification_failure | O5, O6 | hard | wrong evidence |
| SC-13 | Recovery requiring an adaptive plan change | recovery_and_replanning | O2, O5, O6 | hard | error + replan |
| SC-14 | Ambiguous goal requiring clarification | ambiguous_goal | O1, O5, O6 | medium | — |
| SC-15 | State-changing operation requiring approval | confirmation_required | O4, O5, O6 | medium | — |
| SC-16 | Longer multi-step chain, mixed tool types | multi_step | O2, O3, O4, O5, O6 | hard | — |
| SC-17 | Infeasible goal within the capability boundary | infeasible_goal | O1, O5, O6 | medium | — |
| SC-18 | Request outside the declared scope | scope_boundary | O1, O5, O6 | medium | — |

### Required-category coverage check

| Required category | Covered by |
|---|---|
| Simple natural-language task requests | SC-01 |
| Multi-step task requests | SC-02, SC-16 |
| Dependency ordering | SC-03, SC-16 |
| Document-grounded questions | SC-04, SC-10 |
| Questions with insufficient document evidence | SC-05 |
| Data analysis requests | SC-06 |
| Invalid inputs | SC-07 |
| Unknown tool requests | SC-08 |
| Tool execution failures | SC-09 |
| Transient failures | SC-10 |
| Permanent failures | SC-11 |
| Verification failures | SC-12 |
| Recovery and replanning | SC-13, SC-09, SC-10 |
| Ambiguous user goals | SC-14 |
| Confirmation-required operations | SC-15 |

All fifteen required categories are covered. Infeasible goals (SC-17) and scope
boundaries (SC-18) are included as additional coverage.

## 5. Corpus

Scenarios reference the version-controlled sample corpus in `data/sample/`:

| File | Content | Used by |
|------|---------|---------|
| `product_manual.md` | Synthetic product manual with a 24-month warranty and 5 exclusions | SC-01, SC-04, SC-09, SC-10, SC-12, SC-13 |
| `meeting_notes.md` | Synthetic meeting notes with 6 action items and named owners | SC-03, SC-16 |
| `sales_2026.csv` | Synthetic sales data, 26 rows, 4 regions | SC-06, SC-11 |

All three are **generated fixtures authored for this project**. None is
sourced from a third party, and none contains real personal or commercial data.
`data/raw/` is reserved for user-provided documents and is not committed.

## 6. Relationship to the research documents

| Scenario property | Defined in |
|---|---|
| Terminal states (`success`/`failed`/`refused`) | `docs/research/evaluation_metrics.md` |
| Conditions A/B/C | `docs/research/research_methodology.md` |
| Trial counts and test matrix | `docs/research/experimental_design.md` |
| Per-metric operational definitions | `docs/research/evaluation_metrics.md` |
| Threat to validity (e.g. scenario bias) | `docs/research/research_methodology.md` §8 |

## 7. Validation

`tests/unit/test_scenarios.py` validates every scenario file: required fields
present, enumerated values valid, metric keys matching the seven dependent
variables, and cross-file uniqueness of `scenario_id`. The suite is therefore
checked by the test suite rather than by manual inspection alone.

## 8. Plan for expansion

Before the Second Review (23–25 October 2026) the suite must be expanded to
at least 15 scenarios **with repeated trials**; the 18 definitions here satisfy
the definition count, and the harness (Day 7) will run each across the three
conditions with N ≥ 5 trials. Any scenario added later must follow the same
file format and include `adversarial_notes`.
