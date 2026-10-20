# Research Hypothesis

**Project:** NexusAI  
**Document status:** Draft v0.1 — Phase 0 research foundation  
**Date:** 2026-10-20

## 1. Working hypothesis

> **H₁ (alternative hypothesis):** A hybrid AI workflow architecture combining local LLM reasoning, ML-based intent classification, retrieval-augmented generation, controlled tool execution, independent verification, and adaptive replanning can improve the reliability of multi-step task automation compared with simpler rule-based and LLM-only approaches.

> **H₀ (null hypothesis):** There is no measurable difference in reliability between the hybrid NexusAI architecture and rule-based or LLM-only baselines on the defined dependent variables (task completion, planning quality, tool-selection accuracy, verification accuracy, recovery effectiveness, evidence accuracy, execution time).

This is treated as a **hypothesis to investigate, not an already proven conclusion**. The experimental design (see `experimental_design.md`) must be capable of producing evidence that refutes H₁.

## 2. Construct definitions

| Construct | Operational definition (for measurement) |
|-----------|------------------------------------------|
| Reliability | Composite of task completion rate, verification accuracy, and recovery effectiveness across repeated trials. |
| Local LLM reasoning | Inference executed on available local hardware, bounded by CPU/RAM/GPU; no mandatory remote API. |
| ML-based intent classification | A trained or fine-tuned classifier mapping natural-language input to intent classes (separate from generative planning). |
| RAG | Retrieval of relevant chunks from a user-provided local corpus, injected into the generation prompt. |
| Controlled tool execution | Tools registered with input schemas; inputs validated before execution; state-changing tools require user approval. |
| Independent verification | Each step outcome checked against a defined criterion by a verification module distinct from the planner. |
| Adaptive replanning | On verified failure, the planner revises the step sequence within a bounded retry budget. |
| Rule-based baseline | Deterministic, hand-crafted trigger→action workflows with no LLM or learning component. |
| LLM-only baseline | Generative planning and execution with no intent classifier, no RAG, no validation, no independent verification, and no bounded replanning. |

## 3. Testability and falsifiability

H₁ is testable because each construct above maps to a measurable dependent variable and a comparable experimental condition (A: rule-based, B: LLM-only, C: hybrid). H₁ is falsifiable because the same metrics can show the hybrid system performing equal to or worse than a baseline under identical scenarios.

No result will be assumed, and no experiment will be designed to guarantee H₁.

## 4. Assumptions

- "Reliability" can be approximated by the composite of the six named metrics.
- Baselines can be implemented faithfully enough to serve as comparators.
- Evaluation scenarios are representative enough of "everyday multi-step tasks" to draw preliminary conclusions.

## 5. Limitations

- A single MSc-scale implementation cannot establish general reliability across all task domains.
- Results are specific to the chosen toolset, document corpus, and LLM(s).
- The hypothesis does not claim superiority in execution time; the hybrid system may be slower, which is an acceptable trade-off if reliability improves.

---

**Traceability:** Hypothesis maps to experimental factors (independent/dependent variables) in `experimental_design.md` and to metrics in `evaluation_metrics.md`.