# NexusAI

**Working title:** NexusAI: AI-Powered Personal Task Automation  
**Status:** Phase 1 — Day 1 engineering foundation complete  
**MSc Data Science project**  
**Second Review:** 23–25 October 2026

## What NexusAI Is

NexusAI is an AI-powered personal task automation platform that transforms natural-language goals into structured, executable, verifiable, and adaptive workflows. It interprets user intentions, decomposes complex goals into smaller tasks, identifies suitable tools, executes approved operations, verifies outcomes, recovers from failures, and produces a transparent execution report.

## Research Question

> **"Can an AI-driven workflow engine autonomously decompose, execute, verify and adapt multi-step everyday tasks using heterogeneous real-time information?"**

This is treated as a hypothesis to investigate, not a conclusion to assume.

## Research Objectives

| ID | Objective |
|----|-----------|
| O1 | Interpret natural-language user goals and classify task intent. |
| O2 | Decompose goals into executable, dependency-aware steps. |
| O3 | Integrate RAG over user-provided documents. |
| O4 | Secure tool execution with registered tools and validated inputs. |
| O5 | Execution verification, bounded retries, failure handling, adaptive replanning. |
| O6 | Evaluate with measurable metrics (completion, planning quality, tool-selection accuracy, verification accuracy, recovery effectiveness, evidence accuracy, execution time). |

## Architecture Overview

```
Goal Intake → Intent Router → Planner → RAG Module → Tool Registry → Executor → Verifier → Replanner → Report Generator
              (classifier +          (typed plan        (local corpus    (validated      (approval      (independent   (bounded       (auditable
               LLM fallback)         schema + deps)     retrieval)       schemas)       gates)         criterion)     retries)       execution report)
```

**Components** (see `docs/architecture/system_overview.md`):
- **Goal intake** — Natural-language input with minimal sanitisation
- **Intent router** — ML classifier with LLM fallback for out-of-taxonomy inputs
- **Planner** — Structured, dependency-aware plan schema with declared expected outcomes
- **RAG module** — Local document corpus indexing and retrieval with cited passages
- **Tool registry** — Registered tools with input schemas; intent-to-tool resolution
- **Executor** — Schema validation, user approval gates, tool execution, output capture
- **Verifier** — Independent criterion-based verification separate from planner
- **Replanner** — Adaptive replanning within bounded retry budget
- **Report generator** — Transparent execution report with evidence per step

## Technology Stack

- **Language:** Python 3.11+
- **Web framework:** FastAPI 0.115+
- **ASGI server:** Uvicorn 0.30+
- **Validation & Settings:** Pydantic 2.9+, Pydantic Settings 2.5+
- **Database:** SQLite (local-first) via SQLAlchemy 2.0+
- **UI:** Streamlit 1.38+
- **Testing:** pytest 8+, pytest-cov
- **Linting:** Ruff 0.6+
- **HTTP client:** httpx 0.27+

**Constraints:** Python-only implementation. No Java, JavaScript, TypeScript, React, or Node.js. Open-source and local-first. No mandatory paid API, paid database, or AWS dependency.

## Installation

```bash
# Clone the repository
git clone https://github.com/rithwik-nambiar-26/NexusAI.git
cd NexusAI

# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/macOS

# Install dependencies
pip install -e .[dev]
```

## Local Execution

### CLI Commands
```bash
# Show help
python -m nexusai --help

# Print version
python -m nexusai version

# Show configuration and dependency status
python -m nexusai status

# Initialise the SQLite database schema
python -m nexusai init-db

# Start the FastAPI server (development)
python -m nexusai serve --reload
```

### Streamlit UI
```bash
# Start the Streamlit application
streamlit run nexusai/app/ui/app.py
```

The UI will be available at `http://localhost:8501` by default.

### API Documentation
With the FastAPI server running (`python -m nexusai serve`):
- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness/readiness probe |
| GET | `/api/v1/system/status` | Detailed system status with service probes |
| POST | `/api/v1/workflows` | Create a workflow run |
| GET | `/api/v1/workflows` | List workflow runs (paginated, filterable) |
| GET | `/api/v1/workflows/{run_id}` | Get a workflow run with steps |
| DELETE | `/api/v1/workflows/{run_id}` | Delete a workflow run |

## Testing

```bash
# Run full test suite
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=nexusai --cov-report=term-missing

# Run specific test types
python -m pytest tests/unit/ -v        # Unit tests (44)
python -m pytest tests/integration/ -v # Integration tests (23)
python -m pytest tests/e2e/ -v         # E2E tests (13)

# Linting
python -m ruff check .
python -m ruff format . --check
```

## Project Structure

```
NexusAI/
├── nexusai/                    # Python package
│   ├── __init__.py
│   ├── __main__.py             # CLI entry point
│   ├── app/
│   │   ├── config.py           # Pydantic Settings
│   │   ├── main.py             # FastAPI factory
│   │   ├── core/               # Logging, middleware, exceptions, context
│   │   ├── api/                # Routes, schemas, dependencies
│   │   ├── db/                 # Models, session, repositories
│   │   ├── services/           # System, workflow services
│   │   └── ui/                 # Streamlit app + 6 pages
│   ├── agents/                 # Placeholder (Day 2+)
│   ├── ml/                     # Placeholder (Day 2+)
│   ├── rag/                    # Placeholder (Day 4)
│   └── tools/                  # Placeholder (Day 5)
├── tests/                      # 204 tests (unit/integration/e2e)
├── experiments/
│   ├── scenarios/              # 18 evaluation scenarios (versioned)
│   ├── datasets/               # Dataset documentation
│   ├── results/                # Aggregated metrics (versioned)
│   └── scripts/                # Experiment scripts
├── data/
│   ├── sample/                 # Sample documents (versioned)
│   └── raw/processed/          # Local-only (gitignored)
├── artifacts/                  # Model weights, vector stores (gitignored)
├── docs/                       # Research, architecture, project management
│   ├── research/               # 11 research documents
│   ├── architecture/           # System overview, decisions
│   └── project_management/     # Plans, traceability, checkpoints
├── pyproject.toml              # Project config, deps, pytest, ruff
├── CLAUDE.md                   # Development instructions
├── README.md
├── .gitignore
└── .env.example                # Safe environment template
```

## Research Documentation

All research foundation documents are in `docs/research/`:
- `problem_statement.md` — Formal problem definition
- `research_questions.md` — RQ1 + 6 sub-questions
- `research_hypothesis.md` — H₁/H₀ with construct definitions
- `objectives_and_scope.md` — O1–O6, scope, constraints
- `literature_review.md` — Narrative synthesis
- `literature_matrix.md` — 26 candidate works (**all require external verification**)
- `research_gap.md` — Gap statement + contributions C1–C7
- `research_methodology.md` — Conditions A/B/C, variables, threats
- `experimental_design.md` — Test matrix (225 runs minimum), procedure, pass criteria
- `evaluation_metrics.md` — 7 operational metrics
- `data_collection_plan.md` — Categories, procedure, privacy, reproducibility

## Implementation Roadmap (Phase 1)

| Day | Focus | Deliverable |
|-----|-------|-------------|
| **Day 1** ✅ | Project scaffolding, FastAPI, SQLite, Streamlit UI, tests | **Complete** — this commit |
| Day 2 | Intent router (classifier + LLM fallback) | Intent module, classifier accuracy |
| Day 3 | Planner (typed plan schema, dependencies) | Planner module, schema conformance |
| Day 4 | RAG module (indexing, retrieval, citations) | RAG module, evidence accuracy |
| Day 5 | Tool registry + executor (validation, approval) | Executor, tool-selection accuracy |
| Day 6 | Verifier + replanner (bounded retries) | Verifier/replanner, recovery metrics |
| Day 7 | Report generator, experiment harness, first test-matrix pass | End-to-end run, preliminary metrics |

See `docs/project_management/seven_day_implementation_plan.md` for full details.

## Research Disclaimer

**This is an academic research project (MSc Data Science).** The primary research question and hypothesis (H₁) are **not established results** — they are hypotheses to be investigated through controlled experimentation comparing three architectural conditions:

- **Condition A:** Rule-based baseline (deterministic, no LLM)
- **Condition B:** LLM-only baseline (generative, no verification)
- **Condition C:** Hybrid NexusAI (classifier + planner + RAG + validation + verification + replanning)

**No experimental results, benchmarks, or comparative claims are made in this repository.** The literature matrix entries are provisional and require verification against primary sources before citation. All evaluation scenarios are synthetic ground-truth definitions for controlled experimentation, not real user data.

## Current Implementation Status

### Implemented (Day 1)
- ✅ Python project configuration with `pyproject.toml`, `ruff`, `pytest`
- ✅ FastAPI backend with health, system status, and workflow-run APIs
- ✅ SQLite persistence (WorkflowRun + ExecutionStep models with relationships)
- ✅ Streamlit application shell with 6 pages (Overview, Task Automation, Document Intelligence, Data Intelligence, Run History, System Status)
- ✅ Structured logging with request-correlation IDs and secret redaction
- ✅ Centralised Pydantic settings with `.env` support (never committed)
- ✅ Centralised exception handling with consistent JSON error shapes
- ✅ Request ID middleware (propagation + context variable)
- ✅ 204 passing tests (unit, integration, e2e, UI smoke)
- ✅ 18 evaluation scenarios with full ground-truth validation (exceeds 15 minimum)
- ✅ Clean Ruff linting

### Planned (Days 2–7)
- ⏳ Intent router with ML classifier + LLM fallback
- ⏳ Structured planner with typed plan schema and dependency resolution
- ⏳ RAG module with local corpus indexing and cited retrieval
- ⏳ Tool registry with schema validation and user approval gates
- ⏳ Independent verifier and bounded adaptive replanner
- ⏳ Execution report generator and experiment harness
- ⏳ First full test-matrix execution (Conditions A/B/C)

## License

MIT License — see `pyproject.toml` for declaration.

---

*Academic project — accuracy, research quality, and technical consistency are prioritised over volume of output.*