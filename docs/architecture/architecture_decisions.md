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
| AD-11 | Intent taxonomy of 12 classes: 7 workflow-mapped, 5 special-handling | Accepted (Day 2.2) | Each class maps to a distinct workflow pattern or a distinct refusal; splitting `document_operation` into extraction vs transformation removed a real ambiguity | More classes need more labelled data; classes with 3–4 examples are weakly estimated | O1 |
| AD-12 | TF-IDF + Logistic Regression as the intent baseline, with optional sigmoid calibration | Accepted (Day 2.2) | Best validation macro F1 of the three compared variants (0.639 vs 0.431 and 0.379); open-source and local | Small dataset; several classes score F1 = 0.00 on the held-out test set | O1 |
| AD-13 | Deterministic template-driven task decomposition | Accepted (Day 3) | Reproducible and testable without an LLM; keeps the plan inspectable, which is the point of a typed plan | Templates encode one canonical shape per intent; an unusual request may fit it only approximately | O2 |
| AD-14 | NetworkX for dependency graph construction, cycle detection and topological ordering | Accepted (Day 3) | Mature, open-source graph library; correct directed-cycle semantics (`simple_cycles`, not the undirected `cycle_basis`) | One more dependency, kept within the open-source constraint | O2 |
| AD-15 | Planning is not authorization: approval-gated task types are flagged, never executed | Accepted (Day 3) | Keeps the safety decision with the executor (Day 5) rather than the planner; a destructive request produces no executable plan at all | The executor must honour `requires_approval`; enforcement is Day 5 work | O4, O5 |
| AD-16 | Plan persistence deferred beyond Day 3 | Accepted (Day 3) | Planning is a pure function of its input in Day 3, which makes it fully testable; the Day 1 schema already supports runs and steps | Plans are not retrievable after the response; retrieval endpoints report this honestly | O2 |
| AD-17 | numpy-backed local vector index instead of ChromaDB | Accepted (Day 4) | ChromaDB was installed and evaluated: it pulls in a large dependency tree (OpenTelemetry, Kubernetes, OAuth) for functionality not yet needed, ships an `anonymized_telemetry` module that conflicts with the local-first requirement, and its installation changed unrelated packages. A numpy index is ~100 lines, deterministic, inspectable and keeps the dependency surface small | The index is single-process and in-memory; a much larger corpus would need a different backend | O3 |
| AD-18 | Extractive answers and summaries, with an explicit insufficient-evidence outcome | Accepted (Day 4) | Every claim can be checked against the source; no generative model is required, so the pipeline is testable offline. A generative backend can be added behind the same service interface | Less fluent output than a generative summary; lexical matching can miss paraphrases | O3, O5 |
| AD-19 | Hashing embedder as the default, Sentence Transformers opt-in | Accepted (Day 4) | The whole pipeline works with no model files and no network, which keeps the test suite deterministic; the local model is available for better semantic matching | The hashing embedder matches on lexical overlap, so paraphrases are weaker matches | O3 |
| AD-20 | Single filesystem access policy with configurable allowed roots | Accepted (Day 5) | One place decides what may be read; canonicalisation plus a containment check defeats traversal and symlink escapes. The document API and the executor share one policy instance, so they cannot diverge | Paths outside the configured roots are refused even when they are legitimate; the roots must be configured | O4 |
| AD-21 | Explicit tool registry; nothing executes unless registered | Accepted (Day 5) | A capability name resolves to a handler only through registration, so there is no dynamic dispatch and no path from a plan to an arbitrary function | Every new capability needs a schema, a handler and tests | O4 |
| AD-22 | Approval bound to a fingerprint of the task's validated inputs | Accepted (Day 5) | An approval authorises one specific operation; changing the inputs invalidates it, so a granted approval cannot be reused for a different action | The caller must re-approve after any input change, even a harmless one | O4, O5 |
| AD-23 | In-process duplicate-execution guard, not exactly-once execution | Accepted (Day 5) | Prevents a repeated side effect within one engine's lifetime without introducing a distributed transaction or a durable store | The guard is lost on restart; exactly-once execution would need a transactional store, which is out of scope for an MSc project | O4 |

## 3. Decisions pending (Phase 1)

- RAG embedding model and chunking strategy — settled in Day 4: chunking packs paragraphs into 800-character windows with 100-character overlap; the hashing embedder is the default and Sentence Transformers is opt-in (AD-19).
- Plan schema serialisation and step type vocabulary — partly settled in Day 3: the vocabulary is the `TaskType` enum and the plan serialises through Pydantic (JSON).
- Tool registry format and schema language — settled in Day 5: Pydantic models for the input and output schemas, with a `ToolDefinition` holding the handler, permissions, timeout and retry policy.
- A write or send tool, and the tool schemas that would accompany it. The approval path is implemented and tested, but no state-changing handler exists yet.
- Durable execution history and exactly-once execution.
- Verification criterion language (per-step expected-outcome templates vs. LLM-based checker).
- Local UI: terminal/CLI vs. minimal local interface.
- Whether the Day 2 intent taxonomy is extended or merged, pending more labelled data.
- Whether the document service should be given a generative (LLM) answer backend, and if so which local model.

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