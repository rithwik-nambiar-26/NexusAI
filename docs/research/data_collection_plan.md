# Data Collection Plan

**Project:** NexusAI  
**Document status:** Draft v0.1 — Phase 0 research foundation  
**Date:** 2026-10-20

## 1. Purpose

This plan specifies what data is collected, how it is collected, where it is stored, and how it is handled (retention, consent, privacy) to support the experiments in `experimental_design.md` and the metrics in `evaluation_metrics.md`.

## 2. Data categories

| Category | Description | Source | Sensitivity |
|----------|-------------|--------|-------------|
| Scenario suite | Hand-authored goals with ground truth (expected steps, tools, outcomes, evidence, success criteria) | Researcher-authored, synthetic | Low (synthetic, no personal data) |
| Execution traces | Per-run logs: goal, intent, plan, per-step inputs/outputs/verification, retries, citations, terminal state, timestamps | Experiment harness (automatic) | Low/Medium (may contain tool outputs) |
| Human verification labels | Independent human labels of step outcomes and evidence support | Human raters | Low (scenario-based, synthetic) |
| RAG corpus | Local documents used for retrieval | User-provided or synthetic | Medium (may contain user-provided content) |
| Experiment results | Aggregated metrics, CIs, p-values, effect sizes, failure-mode coding | Analysis scripts | Low |
| Configuration | LLM model, temperature, max tokens, prompts, tool schemas | Experiment config | Low |

## 3. Collection procedure

1. **Scenario suite:** author scenarios in `experiments/scenarios/` with YAML/JSON ground-truth files. Record intent class, required tools, required documents, expected outcomes, success criteria.
2. **RAG corpus:** place documents under `experiments/corpus/`; record provenance (author, date, source) for each document; do not include real personal data.
3. **Execution runs:** the harness automatically writes one trace file per run to `experiments/runs/<run_id>.jsonl` or `.json`.
4. **Human verification:** raters label step outcomes and evidence support using a rubric; labels stored under `experiments/labels/`.
5. **Aggregation:** analysis scripts read traces and labels, compute metrics, write results to `experiments/results/`.

## 4. Storage and retention

- All experiment data is stored locally under `experiments/`.
- `experiments/` is **excluded from git** via `.gitignore` (raw traces, labels, results may contain tool outputs or user-provided content and must not be committed).
- Configuration and scenario definitions (non-sensitive) are committed.
- Retention: raw traces retained for the duration of the project plus the review period; deleted or archived after submission unless the user instructs otherwise.

## 5. Privacy and consent

- No real personal user data is collected without explicit consent.
- Any user-provided document used in evaluation is treated as sensitive: not committed, not shared, processed locally only.
- No credentials, API keys, or secrets are ever stored in experiment data or committed (see `.gitignore`).
- The system does not log personally identifying information beyond what the user intentionally places in goals/documents.

## 6. Data quality

- Ground-truth files are reviewed by a second person before use (to catch authoring errors).
- Trace schema is versioned; older trace formats are migrated or noted.
- Missing or malformed traces are logged and excluded with reason, not silently dropped.

## 7. Reproducibility

- Scenario files, corpus file list, experiment config, and analysis scripts are committed to git.
- Raw run outputs are regenerable by re-running the harness; random seeds are recorded per trial.

---

**Traceability:** Scenario suite maps to `experimental_design.md` Section 5; metrics map to `evaluation_metrics.md`; privacy rules implement the non-negotiable constraints (no secrets committed, local-first).

## 8. Review evidence

Before the Second Review, the following must exist as supporting evidence:

- `experiments/scenarios/` with ≥ 15 scenario ground-truth files.
- `experiments/corpus/` with provenance recorded.
- One full pass of the test matrix with traces stored under `experiments/runs/`.
- Aggregated metric results under `experiments/results/`.

None of the above is committed to git; they are listed here as *required local evidence* for the review-readiness matrix.