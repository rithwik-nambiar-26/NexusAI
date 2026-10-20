# Research Questions

**Project:** NexusAI  
**Document status:** Draft v0.1 — Phase 0 research foundation  
**Date:** 2026-10-20

## 1. Primary research question (working)

> **"Can an AI-driven workflow engine autonomously decompose, execute, verify and adapt multi-step everyday tasks using heterogeneous real-time information?"**

This question is the central inquiry of the project. It is intentionally scoped to "everyday tasks" (personal productivity scale) and "heterogeneous real-time information" (user documents plus tool-mediated data) to remain achievable within an MSc Data Science project.

## 2. Sub-questions

| ID | Sub-question | Rationale / what it isolates |
|----|--------------|------------------------------|
| RQ1.1 | To what extent can natural-language goals be decomposed into structured, dependency-aware executable steps? | Isolates planning quality (Objective O2). |
| RQ1.2 | How accurately can an ML-based intent classifier and/or LLM infer task intent from natural-language input? | Isolates intent classification (Objective O1). |
| RQ1.3 | Does RAG over user-provided documents improve step correctness and evidence accuracy versus generation without retrieval? | Isolates RAG contribution (Objective O3). |
| RQ1.4 | Can registered tools be executed with validated inputs and user approval without unsafe or invalid invocations? | Isolates tool validation and security (Objective O4). |
| RQ1.5 | How effective are verification, bounded retries, and adaptive replanning at recovering from step failures? | Isolates verification/recovery (Objective O5). |
| RQ1.6 | Which measurable metrics (task completion, planning quality, tool-selection accuracy, verification accuracy, recovery effectiveness, evidence accuracy, execution time) best characterise system performance? | Defines evaluation (Objective O6). |

## 3. Scope and measurability notes

The primary research question is **measurable** through the dependent variables defined in `experimental_design.md` and evaluated using the metrics in `evaluation_metrics.md`. It is **falsifiable**: experiments are designed to compare the hybrid NexusAI architecture against rule-based and LLM-only baselines, and the results are capable of showing that the hybrid approach does **not** outperform the baselines.

No change to this research question will be made silently. If a scope or measurability problem is identified during development, the issue will be documented here and an academically defensible refinement proposed before proceeding.

## 4. Relationship to hypothesis

The research hypothesis (see `research_hypothesis.md`) is a positive, testable statement derived from these questions. The experiments must be capable of supporting or refuting the hypothesis; they are not designed to confirm it by construction.

## 5. Assumptions

- "Everyday tasks" are bounded in complexity (tens of steps, not hundreds) and duration (minutes to hours).
- "Heterogeneous real-time information" includes local user documents and outputs of registered tools at execution time.
- "Autonomously" means with minimal user intervention, subject to approval gates for tool execution; it does not mean fully unsupervised.

## 6. Limitations

- Findings will be specific to the implemented architecture, toolset, and evaluation scenarios; they do not generalise to all AI workflow systems.
- The question does not address long-horizon planning (days/weeks) or multi-agent coordination.

---

**Traceability:** RQs map to Objectives O1–O6 (see `objective_traceability_matrix.md`) and to experimental factors in `experimental_design.md`.