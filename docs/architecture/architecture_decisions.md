# Architecture Decisions

**Project:** NexusAI  
**Document status:** Draft v0.1 — Phase 0 research foundation  
**Date:** 2026-10-20

## 1. Purpose

Records significant architectural decisions, the alternatives considered, the rationale, and the trade-offs. This is a living record: decisions are added as they are made, and each is linked to the research objective it serves. No implementation work has begun yet; this document captures the intended direction for Phase 1.

## 2. Decision register

| ID | Decision | Status | Rationale | Trade-offs | Objective |
|----|----------|--------|-----------|------------|-----------|
| AD-01 | Python-only implementation | Proposed | Satisfies non-negotiable constraint; rich ecosystem for ML/RAG/tooling | Limits frontend options to local/terminal-based UIs | All |
| AD-02 | Local-first, no mandatory remote API or paid database | Proposed | Satisfies non-negotiable constraint; keeps data on user's machine | Optional local LLM bounded by hardware; no cloud scalability | All |
| AD-03 | Structured, typed plan schema with declared dependencies and expected outcomes | Proposed | Makes plans inspectable and gives the verifier an explicit target; replaces free-form chain-of-thought | More engineering than unstructured LLM output; schema must be maintained | O2, O5 |
| AD-04 | Independent verification module, separate from the planner | Proposed | Avoids circular self-reported success; follows test-based verification precedent | Adds a component to maintain; verification criteria must be defined per step type | O5 |
| AD-05 | Bounded retries with adaptive replanning and finite budget | Proposed | Guarantees termination; makes recovery observable and measurable | Bounded budget may leave some failures unrecovered | O5 |
| AD-06 | Registered tool set with input-schema validation and user approval gates | Proposed | Prevents invalid/unsafe invocations before execution; user remains in the loop | Adds latency and friction for state-changing tools | O4 |
| AD-07 | Hybrid intent routing: ML classifier + LLM fallback | Proposed | Fast, deterministic routing for known intents; LLM handles generalisation | Two components to maintain; classifier taxonomy must be curated | O1 |
| AD-08 | RAG over local user document corpus with cited passages | Proposed | Grounds step evidence in user-provided documents; traceable citations | Retrieval quality bounds step correctness; chunking/embedding choices to tune | O3 |
| AD-09 | Execution report as a first-class output | Proposed | Makes every action auditable; supports the review criteria for transparency | Report generation is additional engineering | O5/O6 |
| AD-10 | No modification of FCC configuration, provider routing, model aliases, or credentials | Proposed | Satisfies non-negotiable constraint | Development must work within existing FCC setup | Process |

## 3. Decisions pending (Phase 1)

- Specific intent taxonomy and classifier model (scikit-learn logistic regression vs. sentence-transformer encoder vs. zero-shot LLM classification).
- RAG embedding model and chunking strategy (bounded by hardware-aware constraint).
- Plan schema serialisation (JSON/YAML) and step type vocabulary.
- Tool registry format and schema language (JSON Schema vs. Pydantic vs. dataclasses).
- Verification criterion language (per-step expected-outcome templates vs. LLM-based checker).
- Local UI: terminal/CLI vs. minimal local interface.

Each pending decision will be recorded here with rationale before implementation.

## 4. Constraints that shape all decisions

- Python 3.11+ only.
- Open-source dependencies preferred; local execution preferred.
- No mandatory paid API, paid database, or AWS dependency.
- FCC configuration untouched.
- No secrets or credentials committed.
- Optional local LLM is hardware-aware (CPU/RAM/GPU bounded).

---

**Traceability:** Decisions AD-01–AD-10 map to objectives O1–O6 and to contributions C1–C7 in `research_gap.md`.