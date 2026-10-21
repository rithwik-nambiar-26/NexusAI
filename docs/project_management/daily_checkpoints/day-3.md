# Day 3 checkpoint — 2026-10-21 (Structured AI Planning and Task Decomposition)

**Day 3 objective:** Structured AI planning and task decomposition (O2).
**Starting commit:** `f064d1f`
**This checkpoint was produced in two parts.** The implementation was
interrupted by a network connectivity failure part-way through; this
document records the complete work, distinguishing what was already in place
when execution resumed from what was completed afterwards. See §10.

## 1. Completed

- **Planner schemas** (`nexusai/ml/planner/schemas.py`):
  - `Plan` — plan_id, original_request, intent, plan_status, tasks,
    dependencies, execution_order, parallel_levels, missing_information,
    unsupported_operations, clarification_required, clarification_question,
    validation_errors, requires_approval, approval_reasons, created_at,
    updated_at, source
  - `Task` — task_id, task_name, description, task_type, input_parameters,
    expected_output, dependencies, required_capabilities,
    verification_criteria, status, assigned_tool, result, error
  - `TaskParameter`, `TaskType`, `TaskStatus`, `PlanStatus` enums
  - `SUPPORTED_TASK_TYPES` (18 task types) and
    `APPROVAL_REQUIRED_TASK_TYPES` (2 task types)
  - `Plan.validate()` recomputes the execution order and parallel levels
    from the resolved dependency graph, so the recorded order always matches
    the recorded dependencies

- **Dependency resolution** (`nexusai/ml/planner/dependencies.py`), NetworkX-based:
  - `build_dependency_graph()` — directed graph, one node per task
  - `resolve_dependencies()` — returns a `DependencyReport` with
    `is_valid`, `errors`, `execution_order`, `parallel_levels`,
    `missing_dependencies`, `self_dependencies`, `duplicate_task_ids` and
    `cycles`
  - Detection of duplicate task ids, missing dependency references,
    self-dependencies and directed cycles
  - `nx.lexicographical_topological_sort` for a deterministic execution order
  - `compute_parallel_levels()` — groups tasks that could run concurrently
    (identification only; Day 3 executes nothing concurrently)
  - `find_independent_tasks()` — public helper for parallelisable groups

- **Planning service** (`nexusai/ml/planner/service.py`):
  - `PlannerService` — deterministic, template-driven decomposition with one
    registered template per supported intent
  - `PlanningStrategy` protocol — the seam where an alternative planning
    backend (for example a local LLM planner) can be substituted without
    changing callers
  - Intent integration that respects the Day 2 classifier status:
    `confident` plans, `low_confidence` plans but records `source`,
    `clarification_required` / `abstained` / `error` do not plan
  - Missing-information detection (document path, dataset path, measure,
    research topic, recipient) that ignores file names when looking for
    topical markers
  - Unsupported-operation detection
  - Safety rules: approval-gated task types, and special-handling intents
    that produce no tasks at all

- **API integration**:
  - `nexusai/app/api/routes/planner.py` — `POST /api/v1/planner/plan`,
    `GET /api/v1/planner/status`, `GET /api/v1/planner/{plan_id}`,
    `POST /api/v1/planner/{plan_id}/task-status`
  - `nexusai/app/api/schemas/planner.py` — `PlanRequest`, `PlanResponse`,
    `PlanStatusResponse`, `TaskStatusUpdate`
  - `nexusai/app/main.py` — planner router registered, `planner` OpenAPI tag
  - The plan route classifies the request with the Day 2 intent service when
    no explicit intent is supplied, and forwards the structured result
    including status and confidence

- **Dependency added**: `networkx>=3.0,<4.0` in `pyproject.toml` (open
  source, no paid or cloud dependency).

- **Documentation**:
  - `docs/architecture/planner_design.md` — plan schema, decomposition
    approach, dependency resolution, validation rules, safety policy, API
    surface, and what is explicitly not implemented
  - `docs/architecture/system_overview.md` — updated with implementation
    status per component
  - `docs/architecture/architecture_decisions.md` — AD-11 to AD-16 recorded
  - `docs/project_management/objective_traceability_matrix.md` — O1 and O2
    rows updated with Day 2.2 and Day 3 evidence

- **Lint cleanup carried out on Day 2 files** (surfaced by running the
  configured Ruff rules over the whole tree): removed duplicated imports and
  unused variables in `nexusai/ml/train.py`, removed an unused local in
  `nexusai/ml/dataset.py`, and moved the project enums to `enum.StrEnum`
  (Python 3.11+, which the project already requires).

## 2. Objectives Advanced

- **O2** — Structured task planning with dependencies: **IMPLEMENTED**
  - Typed plan schema with declared dependencies, expected outputs and
    verification criteria per task
  - Deterministic decomposition into 2–5 typed tasks for all 7 supported
    intents
  - Explicit dependency graph with a validated topological execution order
  - Structural validation: duplicate ids, missing references, self-dependencies,
    cycles, unsupported task types
  - Planning quality is *defined* in `evaluation_metrics.md` but not yet
    *measured*; the measurement harness is Day 7 work

## 3. Metric Results (Preliminary)

| Metric | Value | Evidence |
|--------|-------|----------|
| Tests passing | 325/325 | `python -m pytest tests/` |
| Ruff lint | Clean | `python -m ruff check .` |
| New Day 3 tests | 79 | `test_planner_schemas.py` (19), `test_planner_dependencies.py` (15), `test_planner_service.py` (33), `test_api_planner.py` (12) |
| Supported intents planned | 7 / 7 | `test_each_supported_intent_produces_a_ready_plan` |
| Tasks per plan | 2–5 | `test_each_supported_intent_produces_a_ready_plan` |
| Dependency resolution | 15 unit tests pass | `test_planner_dependencies.py` |
| Cycle detection | Detects and rejects | `test_resolve_detects_two_node_cycle`, `test_resolve_detects_three_node_cycle` |
| Special intents producing tasks | 0 | `test_special_intents_never_produce_tasks` |
| Planning quality (schema conformance) | Not yet measured | Requires the Day 7 harness |

## 4. Verification Evidence

### Dependency graph behaviour (executed)

```
resolve_dependencies(['a','b','c'], [('a','b'),('b','c'),('c','a')])
  is_valid: False
  errors:   ['Cyclic dependency detected involving: a, b, c']
  cycles:   ['b', 'c', 'a']

resolve_dependencies(['a','b','c','d'], [('a','c'),('b','c'),('c','d')])
  is_valid: True
  order:    ['a', 'b', 'c', 'd']
  levels:   [['a', 'b'], ['c'], ['d']]
```

### Planner output (executed)

```
create_plan('Read the product manual and summarise the warranty conditions.',
            intent='document_summarisation', source='explicit')

  plan_status: ready
  tasks: Locate and read the source document (document_read)
         Extract the key points (document_extract)
         Produce the summary (document_summarise)
         Verify the summary against the source (verify_content)
  execution_order: 4 task ids
  parallel_levels: 4 single-task levels
  requires_approval: False
  warnings: []
```

### API (executed)

```
POST /api/v1/planner/plan
  {"text": "Read data/sample/product_manual.md and summarise the warranty conditions.",
   "intent": "document_summarisation", "source": "explicit"}
  -> 200, plan_status=ready, 4 tasks, execution_order length 4
```

## 5. Safety and Approval Handling

| Concern | Implementation |
|---------|----------------|
| Destructive request | `destructive_operation` intent produces an **invalid plan with zero tasks**, `requires_approval=True`, and a confirmation question. No executable plan exists to run. |
| State-changing task | `document_write` and `communication_send` are approval-gated; the plan records `requires_approval` and a reason per task. |
| Plan is not authorization | The planner grants nothing. `requires_approval` is a flag the Day 5 executor must honour. |
| Unsupported task types | Any `TaskType` outside `SUPPORTED_TASK_TYPES` is a validation error, so a malformed or injected type cannot enter a valid plan. |
| Unsupported operations | Requested operations the planner cannot do (code execution, deployment, package installation, recurring scheduling, broadcasting) are listed in `unsupported_operations`. |
| No arbitrary execution | No `eval`, `exec`, `subprocess` or shell access anywhere in the planner. Tasks carry declarative descriptions and `required_capabilities`; they carry no command strings. |
| Tool binding | `required_capabilities` names the tools a task needs, so the Day 5 registry can reject a task whose tool is not registered. |
| Classifier cannot bypass safety | A confident classifier result still routes through the same template and safety rules. The `source` field records where the intent came from. |

## 6. Known Limitations

1. **Templates are one canonical shape per intent.** A request that fits an
   intent only approximately still gets the standard workflow shape.
   Request-specific variation is carried in parameters, not in new task
   shapes. An LLM planner behind `PlanningStrategy` would address this and
   is not implemented.
2. **No plan persistence.** Plans are returned to the caller and not stored,
   so the retrieval endpoints report that they are unavailable. The Day 1
   database schema already supports runs and steps.
3. **No tool binding.** `required_capabilities` names capabilities; the Day 5
   registry resolves them to concrete registered tools.
4. **No concurrent execution.** `parallel_levels` identifies candidates only.
5. **Planning quality not measured.** The `planning_quality` metric is
   defined but conformance scoring needs the Day 7 harness.
6. **Classification quality bounds planning.** The Day 2 classifier scores
   F1 = 0.00 for `data_analysis`, `destructive_operation` and `infeasible`
   on its held-out test set (Day 2.2). A misclassified request therefore
   yields a plan for the wrong workflow. The planner records the intent
   source so this is traceable; the underlying classifier limitation is
   **not** fixed here.
7. **Dependency graphs are linear chains.** Every template produces a
   sequential chain, so `parallel_levels` is always one task per level in
   practice. The parallel detection is implemented and tested, but no
   template currently produces genuinely independent tasks.

## 7. Blockers / Open Items

- None blocking Day 3 completion.
- The classification-quality limitation in §6.6 is inherited from Day 2 and
  is not addressed by the planner.

## 8. Definition of Done Met?

**Yes** for the Day 3 scope:

- Typed Pydantic planning schemas ✅
- Natural-language request to structured task decomposition ✅
- Intent classifier integration ✅
- Task dependency graph ✅
- Topological execution ordering ✅
- Missing dependency detection ✅
- Duplicate task id detection ✅
- Self-dependency detection ✅
- Cycle detection ✅
- Plan validation ✅
- Clarification handling ✅
- Safety and approval flags ✅
- FastAPI planner integration ✅
- Unit, integration and API tests ✅
- Architecture and research documentation ✅

## 9. Git

- Commit message: `feat(planner): implement structured task planning`
- Commit hash: (recorded after commit creation)
- Working tree: clean after commit

## 10. Continuation Record

Day 3 was interrupted by a network connectivity failure. On resumption the
working tree was inspected rather than reset, and the following state was
found and preserved:

**Already complete before the interruption**
- `nexusai/ml/planner/schemas.py` — plan and task schemas
- `nexusai/ml/planner/service.py` — planner service and task templates
- `nexusai/ml/planner/__init__.py` — module exports
- `nexusai/app/api/schemas/planner.py` — API schemas
- `nexusai/app/api/routes/planner.py` — API routes
- `nexusai/app/main.py` — router registration and OpenAPI tag

**Completed after resumption**
- Replaced the inline Kahn's algorithm with a NetworkX-backed
  `dependencies.py` module (AD-14), and fixed directed-cycle detection:
  `nx.cycle_basis` is undirected-only and raised `NetworkXNotImplemented`,
  so it was replaced with `nx.simple_cycles`
- Added `parallel_levels`, `missing_information` and
  `unsupported_operations` to the `Plan` schema
- Added `SUPPORTED_TASK_TYPES` and `APPROVAL_REQUIRED_TASK_TYPES`
- Added classifier integration to the plan route and the planner service,
  including the clarification/abstention/error paths
- Added missing-information and unsupported-operation detection, including
  the fix that stops `sales_2026.csv` from reading as a request for a
  sales measure
- Added `networkx` to `pyproject.toml` and installed it
- Wrote 79 new tests across four files
- Cleared the remaining Ruff findings, which included real defects in
  `nexusai/ml/train.py` (duplicated imports, undefined `Any`, unused
  variables) and `nexusai/ml/dataset.py` (unused local)
- Wrote `docs/architecture/planner_design.md` and updated the system
  overview, decision register and traceability matrix

**Verified at resumption**
- `git log` confirmed the repository was at `f064d1f` with a clean tree
- No Day 3 commit existed, and nothing had been pushed
- All existing work was untracked or modified but uncommitted; none of it
  was discarded

## 11. Commands Executed

```bash
git status --short --branch
git log --oneline -10
git diff nexusai/app/main.py
pip install "networkx>=3.0,<4.0"          # added to pyproject.toml
python -m pytest tests/ -v --tb=short      # 325 passed
python -m ruff check . --output-format=concise
python -m ruff check . --fix
python -m ruff check . --fix --unsafe-fixes # All checks passed!
python nexusai/ml/train.py                 # still trains and saves the model
```

## 12. Day 4 Dependencies

Day 4 (RAG module) depends on the planner in these ways:

- The planner's document and data tasks name `required_capabilities` such
  as `document.read`, `document.extract` and `llm.summarise`. The Day 4 RAG
  module provides the retrieval behind `document.extract` for the document
  intents, and the retrieval steps in the `research` template
  (`web.search`, `web.fetch`) map onto the same capability.
- Every document workflow ends in a `verify_content` task that expects
  cited evidence. Day 4's retrieval must return traceable spans for that
  verification to be meaningful, and for the `evidence_accuracy` metric in
  `evaluation_metrics.md` to be computable.
- The planner does not bind tools; the Day 5 registry resolves
  `required_capabilities` to registered tools. Day 4 should expose the same
  capability names so the registry can bind them without a translation
  layer.

---

**Conclusion:** Day 3 is complete. The planner produces validated, typed,
dependency-aware plans for every supported intent, rejects structurally
invalid plans, never turns a destructive request into an executable plan,
and never authorizes execution. The Day 2 classifier's documented accuracy
limitations are inherited unchanged and are visible in the plan's `source`
field. Day 4 may begin after review.
