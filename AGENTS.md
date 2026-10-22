# NexusAI — Project Context

**Project:** NexusAI — AI-Powered Personal Task Automation (MSc Data Science)  
**Phase:** Phase 1 in progress — Days 1–5 implemented and committed; Day 5.5 Streamlit review interface integrated

## Working directory

`D:\NexusAI` — this is the repository root.

## Project rules (non-negotiable)

- Python-only application implementation. No Java, JavaScript, TypeScript, React, or Node.js.
- Open-source and local-first. No mandatory paid API, paid database, or AWS dependency.
- Do **not** modify provider routing, model aliases, or credentials.
- Optional local LLM integration must be hardware-aware.
- Never invent research papers, citations, experimental results, or evaluation metrics.

## Docs you should read first

1. `docs/research/problem_statement.md` — the problem being solved
2. `docs/research/research_questions.md` — RQ1 and sub-questions
3. `docs/research/research_hypothesis.md` — H₁ / H₀ (treat as to-investigate, not proven)
4. `docs/research/objectives_and_scope.md` — O1–O6 and scope
5. `docs/research/research_gap.md` — the gap and contributions C1–C7
6. `docs/research/literature_matrix.md` — candidate literature (all entries **require external verification** before citation)
7. `docs/research/research_methodology.md` — variables, conditions A/B/C, design
8. `docs/research/experimental_design.md` — test matrix, procedure, pass criteria
9. `docs/research/evaluation_metrics.md` — metric definitions
10. `docs/research/data_collection_plan.md` — data handling, privacy, reproducibility
11. `docs/architecture/system_overview.md` — component map and data flow
12. `docs/architecture/architecture_decisions.md` — decision register (AD-01…AD-10)
13. `docs/project_management/seven_day_implementation_plan.md` — Day 1–7 plan
14. `docs/project_management/objective_traceability_matrix.md` — O1–O6 traceability
15. `docs/project_management/daily_checkpoints/README.md` — checkpoint template

## Key facts

- Research question: "Can an AI-driven workflow engine autonomously decompose, execute, verify and adapt multi-step everyday tasks using heterogeneous real-time information?"
- Second Review: 23–25 October 2026 (six criteria, 40 marks total)
- Python 3.11.2 available; git repo initialised at `D:\NexusAI`
- Application code exists: Days 1–5 are implemented, tested and committed. Day 6 (verifier/replanner) and Day 7 (experiment harness) are **not** started.
- The research foundation has been reviewed and the Phase 1 implementation has begun.

## Implementation state

| Area | State |
|------|-------|
| Engineering foundation, FastAPI, SQLite, Streamlit (Day 1) | Implemented, tested |
| Intent classification, 12 classes (Days 2–2.2) | Implemented, tested |
| Structured planner with dependency graph (Day 3) | Implemented, tested |
| Document intelligence and local RAG (Day 4) | Implemented, tested |
| Tool registry and controlled execution (Day 5) | Implemented, tested |
| Streamlit review interface (Day 5.5) | Implemented, tested |
| Independent verifier, adaptive replanner (Day 6) | **Not started** |
| Experiment harness and A/B/C evaluation (Day 7) | **Not started** |

Five capabilities are registered, all read-only: `document.read`, `document.extract`,
`llm.summarise`, `data.load`, `data.analyse`.

## Research integrity rules

- H₁ is **to be investigated, not assumed**. No comparative claim about the hybrid
  architecture has been measured.
- The literature matrix entries are provisional and require external verification.
- Report measured results with their support counts. Never report a number that was
  not produced by a run that is recorded in the repository.

## Git

- Commit style: `docs(research): ...`
- Never commit secrets, credentials, or local environment files (`experiments/`, `.env`, `*.key`, etc. are gitignored)
- Commit attribution lines are not mandated by the project; follow your own or your team's conventions.

## Development environment

- Use your preferred development tools and AI assistants.
- Do not modify provider routing, model aliases, or credentials.
- The project has no mandatory AI tool dependency.