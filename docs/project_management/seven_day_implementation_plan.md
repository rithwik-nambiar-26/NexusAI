# Seven-Day Implementation Plan

**Project:** NexusAI  
**Document status:** Draft v0.1 — Phase 0 research foundation  
**Date:** 2026-10-20  
**Review date:** 23–25 October 2026 (Second Review)

## 1. Purpose

A concrete, time-boxed plan for Phase 1 implementation. It maps directly to the research objectives and is structured so that each day ends in a verifiable checkpoint. The plan is ambitious but scoped to what is achievable in one week of MSc-scale development.

**Constraint:** No feature development begins until this research foundation is reviewed and the Phase 0 checkpoint is verified (see `daily_checkpoints/`).

## 2. Daily plan

| Day | Focus | Objectives addressed | Deliverable / checkpoint |
|-----|-------|----------------------|--------------------------|
| Day 1 | Project scaffolding: repo, Python environment, `.gitignore`, CLAUDE.md, package layout, logging | Process / all | Repo scaffolding committed; `python -m nexusai --help` runs |
| Day 2 | Intent router: classifier stub + LLM fallback; intent taxonomy; unit tests | O1 | Intent router module; classifier accuracy measured on labelled examples |
| Day 3 | Planner: structured plan schema, dependency resolution, plan generation | O2 | Planner module; schema-conformance score measured |
| Day 4 | RAG module: local corpus indexing, retrieval, cited passages | O3 | RAG module; evidence accuracy measured on corpus |
| Day 5 | Tool registry + executor: registered tools, schema validation, approval gate | O4 | Executor module; tool-selection accuracy and invalid-invocation rate measured |
| Day 6 | Verifier + replanner: independent verification, bounded retries, adaptive replanning | O5 | Verifier + replanner; verification accuracy and recovery effectiveness measured |
| Day 7 | Report generator, end-to-end integration, experiment harness, first full test-matrix pass | O5/O6 | Execution report; end-to-end run on scenario suite; preliminary metrics |

Each day ends with: code committed, tests run, checkpoint report written in `daily_checkpoints/day-N.md`.

## 3. Milestones

| Milestone | Criterion | Target day |
|-----------|-----------|------------|
| M1 | Scaffolding + CLI entry point | Day 1 |
| M2 | Intent router with tests | Day 2 |
| M3 | Structured planner with schema conformance | Day 3 |
| M4 | RAG with cited passages | Day 4 |
| M5 | Executor with validation + approval gate | Day 5 |
| M6 | Verifier + bounded replanner | Day 6 |
| M7 | End-to-end integration + first experiment pass | Day 7 |

## 4. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Local LLM too slow / hardware insufficient | Medium | High | Design for optional local LLM; default to classifier + rule-based planner first |
| Retrieval quality poor | Medium | Medium | Start with BM25 / TF-IDF over local corpus before embeddings |
| Verification criteria hard to define | Medium | Medium | Use per-step expected-outcome templates; keep verifier rule-based initially |
| Scope creep beyond one week | High | High | Strictly time-box each day; de-prioritise non-Objective work |

## 5. Definition of done for Phase 1

- All seven days completed with checkpoint reports.
- End-to-end run on the scenario suite produces an execution report per scenario.
- All six dependent variables computed at least once (preliminary).
- Code committed; no secrets committed.
- Ready for Second Review evidence (see review-readiness matrix).

---

**Traceability:** Days map to objectives O1–O6; milestones map to checkpoints in `daily_checkpoints/`; risks map to `threats_to_validity` in `research_methodology.md`.