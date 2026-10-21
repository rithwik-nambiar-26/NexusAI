# Day 1 checkpoint — 2026-10-21

## Completed

- **Python project scaffolding**: `pyproject.toml` with build system, dependencies (FastAPI, Uvicorn, Pydantic, Pydantic Settings, SQLAlchemy, Streamlit, httpx, python-multipart), optional dev dependencies (pytest, pytest-cov, ruff), pytest and ruff configuration, package discovery, and console script entry point (`nexusai`).

- **FastAPI application factory** (`nexusai/app/main.py`): `create_app()` builds a FastAPI app with structured logging, SQLite engine/session management (isolated per app instance), CORS middleware, request ID middleware, exception handlers, and three routers (health, system, workflows).

- **Health endpoint** (`GET /health`): Returns liveness/readiness with component checks (database, ollama, chromadb). Reports `ok` when database reachable; `unhealthy` when database unavailable; never claims optional services as available without successful probe.

- **System status endpoint** (`GET /api/v1/system/status`): Returns detailed service status with `available` (probe succeeded), `configured` (URL set), `backend`/`url`/`detail`. Honest probing: unconfigured services report `available=false`, `configured=false`, `detail="not configured"`.

- **Workflow run persistence APIs** (`/api/v1/workflows`):
  - `POST` — create run with goal, optional intent/condition
  - `GET` — list runs with pagination, status/condition filters
  - `GET /{run_id}` — fetch run with execution steps
  - `DELETE /{run_id}` — delete run (cascades steps)

- **SQLite + SQLAlchemy 2.0 models** (`nexusai/app/db/models.py`):
  - `WorkflowRun`: id, request_id, goal, intent, condition, status, terminal_state, plan, retries_used, execution_time_ms, timestamps
  - `ExecutionStep`: id, run_id, step_index, step_id, step_type, tool, input_data, output_data, verification_result, retries_used, error, timestamps
  - Relationship: `WorkflowRun.steps` with cascade delete-orphan, ordered by `step_index`

- **Database session management** (`nexusai/app/db/session.py`): Engine creation with foreign keys pragma, schema initialization, global and per-app engine/session factories, FastAPI dependency (`get_db`), standalone generator (`get_db_standalone`), test isolation support (`reset_engine`).

- **Request ID middleware** (`nexusai/app/core/middleware.py`): Reads/propagates `X-Request-ID`, generates UUID4 if absent, exposes via context variable, echoes on response header, logs request method/path/status with request_id.

- **Structured logging** (`nexusai/app/core/logging.py`): JSON and text formatters with UTC timestamps, request_id filter injection, secret redaction (password/secret/token/api_key/authorization/credentials), idempotent configuration, scoped loggers.

- **Exception handling** (`nexusai/app/core/exceptions.py`): `NexusAIError` base with stable error codes, HTTP status codes, details; subclasses for `ConfigurationError`, `NotFoundError`, `ServiceUnavailableError`, `ValidationError`; consistent JSON error shape with `request_id`; no internal stack traces leaked to clients.

- **Centralised settings** (`nexusai/app/config.py`): Pydantic Settings with `NEXUSAI_` env prefix, `.env` support (gitignored), validated fields (log_level, upload limits, execution limits), repository-root-relative SQLite path resolution, cached singleton with test reset.

- **Streamlit UI shell** (`nexusai/app/ui/app.py`) with 6 pages:
  - **Overview** — project identity, objectives O1–O6, architecture, implemented/planned work, second review date
  - **Task Automation** — goal submission form, captured submission display, run history placeholder
  - **Document Intelligence** — RAG placeholder (Day 4), disabled upload/query controls
  - **Data Intelligence** — tabular data placeholder (Day 4-5), empty dataset table
  - **Run History** — run history placeholder (Day 7), empty table with contract columns
  - **System Status** — reads `GET /api/v1/system/status`, shows service configured/available/detail, limits table

- **18 evaluation scenarios** (`experiments/scenarios/SC-01...SC-18.json`): Each with scenario_id, name, category, difficulty, research_objectives, research_questions, user_input, expected_intent, expected_workflow, expected_plan (min/max steps, must_include_steps, must_include_dependencies), required_tools, required_documents, expected_outcome, expected_output_criteria, failure_conditions, evaluation_criteria (7 metrics), adversarial_notes. Categories cover all 15 required types; outcomes include success/failed/refused; fault injection modes diverse; referenced documents exist; computable scenarios carry ground_truth.

- **Dataset provenance documentation**: `experiments/datasets/README.md` (placeholder for Phase 1), `data/sample/` with `product_manual.md`, `meeting_notes.md`, `sales_2026.csv`.

- **Pytest configuration** (`pyproject.toml`): testpaths, pythonpath, strict markers/config, deprecation warnings as errors, markers (unit/integration/e2e), isolated in-memory SQLite fixtures (`conftest.py`).

- **Ruff configuration** (`pyproject.toml`): line-length 100, py311 target, select E/W/F/I/N/UP/B/C4/SIM/RUF, per-file ignores, isort known-first-party, format double quotes/space indent.

- **Gitignore updated** for research evidence tracking: `experiments/scenarios/`, `experiments/datasets/`, `experiments/results/`, `experiments/scripts/` versioned; `experiments/runs/`, `experiments/corpus/`, local databases excluded; `data/raw/`, `data/processed/` excluded with `.gitkeep`; `artifacts/models/` with `.gitkeep`.

## Objectives advanced

- **O1** — Settings and intent classification infrastructure (classifier stub in agents/, LLM fallback design in architecture_decisions.md AD-07)
- **O2** — WorkflowRun/ExecutionStep persistence schema with dependency-aware step ordering
- **O3** — RAG module placeholder; scenario categories include document_grounded, insufficient_evidence
- **O4** — Tool registry placeholder; workflow API accepts tool/step metadata; architecture_decision AD-06 for validation/approval
- **O5** — Verification fields on ExecutionStep (verification_result, retries_used); replanning budget in Settings
- **O6** — 18 validated scenarios with 7 evaluation criteria each; experiment harness design in experimental_design.md

## Metric results (preliminary)

| Metric | Value | Evidence |
|--------|-------|----------|
| Tests passing | 204/204 | `python -m pytest tests/ -v` |
| Ruff lint | Clean | `python -m ruff check .` |
| Health endpoint (DB reachable) | `status=ok` | `test_health_returns_ok_when_database_reachable` |
| Health endpoint (DB unreachable) | `status=unhealthy` | `test_health_is_unhealthy_when_database_unavailable` |
| System status honesty | Optional services unavailable | `test_system_status_does_not_claim_unavailable_services` |
| Workflow CRUD | All operations work | `test_create_and_fetch_run`, `test_list_runs`, `test_delete_run` |
| Request ID propagation | Header in/out, context | `test_preserves_incoming_request_id`, `test_request_id_is_generated_when_absent` |
| Secret redaction | Passwords/keys redacted | `test_redact_secret_strings` |
| Scenario validation | 18/18 pass schema | `test_suite_exists_and_is_large_enough` (18 ≥ 15) |
| UI smoke tests | All 6 pages render | `test_navigating_to_each_page_renders` |
| No fake UI data | Empty tables confirmed | `test_task_automation_page_does_not_fake_results` |

## Blocker(s)

- None for Day 1 acceptance criteria. All 16 criteria verified (15 implementation + 1 checkpoint doc created here).

## Definition of done met?

**Yes** — All Day 1 acceptance criteria from `seven_day_implementation_plan.md` satisfied:
- Repo scaffolding committed (this commit)
- `python -m nexusai --help` runs
- FastAPI app with health, system, workflow APIs
- SQLite persistence with WorkflowRun/ExecutionStep
- Streamlit UI shell with 6 pages
- Structured logging, request IDs, centralised settings, exception handling
- 204 passing tests, clean ruff
- 18 evaluation scenarios (exceeds 15 minimum)
- Day 1 checkpoint documented (this file)

## Git

- Commit message: `feat(core): establish NexusAI engineering foundation`
- Commit hash: (recorded after commit creation)
- Working tree clean: Yes (after commit)