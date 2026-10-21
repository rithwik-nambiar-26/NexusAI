# System Overview

**Project:** NexusAI  
**Document status:** Draft v0.2 — Phase 1, Days 1–3 implemented  
**Date:** 2026-10-21

## 1. Purpose

A high-level, architecture-agnostic description of the NexusAI system. It defines the major components, their responsibilities, and the data flow from a natural-language goal to an execution report. Detailed component specifications and architecture decisions live in `architecture_decisions.md`.

## 2. Component map

```
+----------------+     +----------------+     +-----------------+
|   Goal intake  | --> | Intent router  | --> | Planner         |
| (natural lang) |     | (classifier +  |     | (structured plan|
+----------------+     |  LLM fallback) |     |  schema + deps) |
                       +----------------+     +-----------------+
                                              |
                                              v
                                       +-------------+
                                       | RAG module  |<--+-- local document corpus
                                       +-------------+   |
                                              |          |
                                              v          |
                                       +-------------+   |
                                       | Tool registry|--+-- registered tools + schemas
                                       +-------------+
                                              |
                                              v
                                       +-------------+
                                       | Executor    |--+-- tool execution + approval gate
                                       +-------------+
                                              |
                                              v
                                       +-------------+
                                       | Verifier    |--+-- independent criterion check
                                       +-------------+
                                              |
                                              v (on failure, within budget)
                                       +-------------+
                                       | Replanner   +-- adaptive replanning
                                       +-------------+
                                              |
                                              v
                                       +-------------+
                                       | Report gen  |--+-- execution report
                                       +-------------+
```

## 3. Component responsibilities

| Component | Responsibility | Objective | Status |
|-----------|---------------|-----------|--------|
| Goal intake | Accepts natural-language goal input; performs minimal sanitisation | O1 | ✅ Day 1 |
| Intent router | Classifies intent (ML classifier) with LLM fallback for out-of-taxonomy inputs | O1 | ✅ Day 2 (ML classifier); LLM fallback pending |
| Planner | Decomposes the goal into a typed, dependency-aware plan with declared expected outcomes | O2 | ✅ Day 3 (see `planner_design.md`) |
| RAG module | Retrieves relevant passages from the local user corpus; returns cited evidence | O3 | ⏳ Day 4 |
| Tool registry | Holds registered tools with input schemas; resolves intent/tool to concrete tool | O4 | ⏳ Day 5 |
| Executor | Validates inputs against schema; enforces approval gates; executes tools; captures outputs | O4 | ⏳ Day 5 |
| Verifier | Independently checks each step's actual output against its declared expected outcome | O5 | ⏳ Day 6 |
| Replanner | On verified failure, revises remaining steps within a bounded retry budget | O5 | ⏳ Day 6 |
| Report generator | Produces the auditable execution report (goal, plan, per-step evidence, verification, retries, outcome) | O5/O6 | ⏳ Day 7 |

The planner introduced in Day 3 is specified in detail in
`planner_design.md`: plan schema, task decomposition templates, NetworkX-based
dependency resolution, validation rules and the safety policy. It plans only
and never authorizes execution.

## 4. Data flow (typical execution)

1. User submits a natural-language goal.
2. Intent router classifies the goal; if low confidence, escalates to LLM-based intent inference.
3. Planner produces a structured plan: ordered steps, each with tool, inputs, dependencies, and expected outcome.
4. RAG module retrieves supporting passages from the local corpus for steps that need document evidence.
5. Executor walks the plan in dependency order:
   - Validates each step's inputs against the tool's schema.
   - For state-changing tools, pauses for user approval before executing.
   - Executes the tool and records the actual output.
6. Verifier checks each actual output against the step's declared expected outcome.
7. On failure, if the retry budget remains, the replanner revises the remaining steps and execution continues; otherwise the step is marked failed.
8. Report generator assembles the execution report: goal, intent, plan, per-step inputs/outputs/verification/citations/retries, terminal state, and execution time.

## 5. Key properties (by design)

- **Local-first:** all components run locally; no mandatory remote API or database.
- **Python-only:** implemented in Python 3.11+; no Java, JavaScript, TypeScript, React, or Node.js.
- **Verifiable:** verification is a component separate from planning; execution reports are auditable.
- **Bounded:** replanning has a finite retry budget; no unbounded loops.
- **Approved:** state-changing tool executions require explicit user approval.
- **Hardware-aware:** optional local LLM integration is bounded by available CPU/RAM/GPU.

## 6. Non-goals (out of scope for Phase 0 / Phase 1)

- Multi-user collaboration or real-time shared workspaces.
- Production web or mobile frontend.
- Mandatory cloud LLM APIs, paid databases, or AWS services.
- Safety-critical, medical, legal, or regulated financial automation.
- Training foundation models from scratch.

## 7. Constraints inherited from project policy

- Python-only implementation.
- Open-source and local-first.
- No mandatory paid API, paid database, or AWS dependency.
- FCC configuration, provider routing, model aliases, and credentials are not modified.
- No secrets, credentials, or local environment files committed to the repository.

---

**Traceability:** Components map to objectives O1–O6; component responsibilities map to contributions C1–C7 in `research_gap.md`; data flow implements the verification-independent design argued in `research_methodology.md`.