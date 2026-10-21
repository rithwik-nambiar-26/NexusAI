# Planner Design

**Project:** NexusAI  
**Document status:** Draft v0.1 — Phase 1, Day 3  
**Date:** 2026-10-21  
**Research objective:** O2 — Structured task planning with dependencies

## 1. Purpose

This document specifies the structured planning component introduced in Day 3:
how a natural-language request and a classified intent become a validated
sequence of typed tasks with an explicit dependency graph. It covers the
plan schema, the decomposition strategy, the dependency resolution
algorithm, the validation rules and the safety policy.

The planner **plans only**. It does not execute tasks, call tools, or
authorize anything. Controlled execution belongs to Day 5.

## 2. Component map

```
                        +---------------------------+
   natural-language --> |  Planning input           |
   request             |  (text, intent, entities)  |
                        +-------------+-------------+
                                      |
                                      v
                        +---------------------------+
                        |  Intent integration        |
                        |  (classifier result or    |
                        |   explicit intent)        |
                        +-------------+-------------+
                                      |
                                      v
                        +---------------------------+
                        |  Task decomposition       |
                        |  (intent -> task template)|
                        +-------------+-------------+
                                      |
                                      v
                        +---------------------------+
                        |  Dependency resolution    |
                        |  (NetworkX graph)         |
                        +-------------+-------------+
                                      |
                                      v
                        +---------------------------+
                        |  Plan validation          |
                        |  (structure + safety)     |
                        +-------------+-------------+
                                      |
                                      v
                        +---------------------------+
                        |  Planning output          |
                        |  (typed Plan object)      |
                        +---------------------------+
```

Implementation locations:

| Stage | Module |
|-------|--------|
| Planning input, output, schemas | `nexusai/ml/planner/schemas.py` |
| Dependency resolution | `nexusai/ml/planner/dependencies.py` |
| Intent integration, decomposition, validation | `nexusai/ml/planner/service.py` |
| API surface | `nexusai/app/api/routes/planner.py`, `nexusai/app/api/schemas/planner.py` |

## 3. Plan schema

`Plan` (in `nexusai/ml/planner/schemas.py`) carries:

| Field | Purpose |
|-------|---------|
| `plan_id` | Unique identifier for the plan |
| `original_request` | The user's request, echoed verbatim |
| `intent` | The intent the plan was built for |
| `plan_status` | `draft`, `validated`, `ready`, `executing`, `completed`, `failed`, `invalid` |
| `tasks` | The typed task list |
| `dependencies` | `(prerequisite_id, dependent_id)` pairs |
| `execution_order` | Topologically sorted task ids |
| `parallel_levels` | Groups of task ids with no dependency between them |
| `missing_information` | Information the plan needs that the request did not supply |
| `unsupported_operations` | Operations requested that the planner cannot support |
| `clarification_required` | Whether the user must clarify before execution |
| `clarification_question` | The question to put to the user |
| `validation_errors` | Structural problems found during validation |
| `requires_approval` | Whether the plan contains state-changing operations |
| `approval_reasons` | Why approval is required |
| `created_at`, `updated_at` | Timestamps |
| `source` | `classifier` or `explicit` — how the intent was obtained |

Each `Task` carries `task_id`, `task_name`, `description`, `task_type`,
`input_parameters`, `expected_output`, `dependencies`,
`required_capabilities`, `verification_criteria`, `status` and `assigned_tool`.

`plan_id` and `task_id` are generated with `uuid4`, so identifiers are unique
per plan. Dependency references are validated against the plan's own task set.

## 4. Task decomposition

Decomposition is **deterministic and template-driven**. Each supported intent
has a registered template listing the task types, names, descriptions,
required capabilities, expected outputs and verification criteria for that
workflow shape. The templates are workflow patterns, not canned answers to
particular requests: the same pattern is reused across many phrasings, and
request-specific detail travels in task parameters and plan-level entity
fields.

| Intent | Tasks | Task types |
|--------|-------|-----------|
| `document_question_answering` | 3 | read → extract → verify |
| `document_summarisation` | 4 | read → extract → summarise → verify |
| `document_extraction` | 3 | read → extract → verify |
| `document_transformation` | 4 | read → transform → write → verify |
| `data_analysis` | 5 | load → analyse → aggregate → verify → export |
| `research` | 5 | query → fetch → extract → synthesise → verify |
| `communication` | 2 | draft → send |

Tasks are chained sequentially: each task depends on its predecessor. The
dependency is recorded twice — once as a `(prerequisite, dependent)` pair on
the plan, and once in the dependent task's `dependencies` list — and
validation checks that the two representations agree.

Every workflow ends in a verification task. This is deliberate: the verifier
must be a component separate from the planner, and a plan that cannot be
verified cannot be checked.

### Extensibility

Adding an intent means adding one template entry. Adding a task type means
adding it to `TaskType` and to `SUPPORTED_TASK_TYPES`. The `PlanningStrategy`
protocol marks the seam where an alternative planning backend (for example a
local LLM planner) can be substituted without changing callers. No such
backend is required to run NexusAI or its tests, and no paid or cloud
inference is involved.

## 5. Dependency resolution

`nexusai/ml/planner/dependencies.py` uses **NetworkX**.

`build_dependency_graph(task_ids, dependencies)` builds a `nx.DiGraph` with
one node per task and one edge per dependency, directed from prerequisite to
dependent.

`resolve_dependencies(task_ids, dependencies)` returns a `DependencyReport`
containing:

| Field | Meaning |
|-------|---------|
| `is_valid` | True when the graph has no structural defect |
| `errors` | One message per defect |
| `execution_order` | Topologically sorted task ids |
| `parallel_levels` | Groups of task ids that may run concurrently |
| `missing_dependencies` | References to task ids that do not exist |
| `self_dependencies` | Task ids that depend on themselves |
| `duplicate_task_ids` | Task ids appearing more than once |
| `cycles` | Task ids participating in a dependency cycle |

Detection order:

1. **Duplicate task ids** — reported once each, in first-seen order.
2. **Missing dependency references** — any referenced id not in the task set.
3. **Self-dependencies** — a task listed as its own prerequisite.
4. **Cycles** — `nx.simple_cycles` enumerates elementary directed cycles
   (`nx.cycle_basis` is undirected-only and is not used). Every node in a
   cycle is recorded.

The execution order is `nx.lexicographical_topological_sort`, which is
deterministic for a given graph, so the same plan always yields the same
order.

`compute_parallel_levels` groups tasks into levels such that no two tasks in
a level depend on one another. This identifies the tasks that a future
execution phase could run concurrently. **Day 3 does not execute anything
concurrently**; the levels are informational.

## 6. Plan validation

`Plan.validate()` returns a list of errors. A plan with any error is marked
`invalid` and must not be executed.

| Rule | Error message |
|------|---------------|
| At least one task | "Plan must contain at least one task" |
| Unique task ids | "Duplicate task id: `<id>`" |
| Dependencies exist | "Dependency references unknown task: `<id>`" |
| No self-dependency | "Self-dependency detected: `<id>`" |
| Acyclic graph | "Cyclic dependency detected involving: `<ids>`" |
| Task-level refs valid | "Task `<id>` depends on unknown task: `<id>`" |
| Task-level no self-dep | "Task `<id>` depends on itself" |
| Known task types | "Unsupported task type: `<type>`" |

Validation recomputes `execution_order` and `parallel_levels` from the
resolved graph, so the recorded order always matches the recorded
dependencies.

## 7. Intent integration

The planner accepts an intent from two sources, and records which was used in
`Plan.source`:

| Source | When | Recorded as |
|--------|------|-------------|
| Classifier | No intent supplied to the API endpoint | `"classifier"` |
| Explicit | Intent supplied by the caller | `"explicit"` |

The API route `POST /api/v1/planner/plan` classifies the request with the
Day 2 intent service when no intent is given, then forwards the structured
classification result — including its status and confidence — to the planner.

The planner does **not** treat a low-confidence prediction as ground truth:

| Classification status | Planner behaviour |
|----------------------|-------------------|
| `confident` | Plan normally |
| `low_confidence` | Plan normally, but `source` remains `classifier` so the consumer can see the intent was inferred rather than supplied |
| `clarification_required` | No plan. An invalid plan with `clarification_required=True` and a clarification question |
| `abstained` / `error` | No plan. An invalid plan carrying the reason |

This means the planner is testable without relying on the classifier being
accurate: an explicit intent bypasses classification entirely, and the
classifier path is exercised in a separate integration test.

The Day 2 classifier's known limitations (small dataset, per-class F1 of 0.00
for `data_analysis`, `destructive_operation` and `infeasible` on the held-out
test set — see `daily_checkpoints/day-2.2.md`) are **not** fixed by this
component. The planner treats a classifier result as a proposal, and the
`source` field records where it came from.

## 8. Safety policy

**Planning is not authorization.** A plan never authorizes execution, and a
confident prediction never bypasses a safety control.

### Approval-gated task types

`APPROVAL_REQUIRED_TASK_TYPES` marks the task types that mutate state:

| Task type | Why it requires approval |
|-----------|--------------------------|
| `document_write` | Writes a file to disk |
| `communication_send` | Sends a message to a third party |

`DATA_EXPORT` is deliberately **not** approval-gated: in the data-analysis
template it renders the answer rather than writing a file.

When a plan contains an approval-gated task, `requires_approval` becomes
true and `approval_reasons` explains why. A future executor must consult
`requires_approval` before running any task; the planner itself grants
nothing.

### Special-handling intents

Intents that cannot become executable plans produce **no tasks at all**:

| Intent | Result |
|--------|--------|
| `destructive_operation` | Invalid plan, `requires_approval=True`, no tasks |
| `infeasible` | Invalid plan, clarification question, no tasks |
| `out_of_scope` | Invalid plan, clarification question, no tasks |
| `channel_unavailable` | Invalid plan, clarification question, no tasks |
| `invalid` | Invalid plan, clarification question, no tasks |

A destructive request never becomes a plan with a `document_write` task that
might be executed. It becomes an invalid plan that asks for explicit
confirmation. The independent approval gate belongs to the executor (Day 5);
this component refuses to produce an executable plan for it in the first
place.

### Structural safety

- The planner contains no `eval`, `exec`, `subprocess` or shell access.
- Tasks carry `required_capabilities` naming the tools they need, so the
  Day 5 registry can reject a task whose tool is not registered.
- Task types are restricted to `SUPPORTED_TASK_TYPES`; an unknown type is a
  validation error, so a malformed or injected task type cannot enter a
  valid plan.
- No task carries a command string to be run. Instructions are declarative
  descriptions, never executable text.

## 9. Missing information and unsupported operations

`missing_information` records what the plan needs that the request did not
supply — for example a document path for a document intent, or the measure
to compute for a data analysis. Detection looks for topical markers in the
request prose with file references stripped out, so a filename such as
`sales_2026.csv` is not mistaken for the user asking for a sales measure.

`unsupported_operations` records operations the request asks for that the
planner cannot support (code execution, script running, package installation,
deployment, recurring scheduling, broadcasting). These are reported rather
than silently dropped.

## 10. API surface

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v1/planner/plan` | Create a structured plan for a request |
| GET | `/api/v1/planner/status` | Report planner availability |
| GET | `/api/v1/planner/{plan_id}` | Report that plan persistence is not implemented |
| POST | `/api/v1/planner/{plan_id}/task-status` | Report that plan persistence is not implemented |

`POST /api/v1/planner/plan` accepts:

| Field | Type | Purpose |
|-------|------|---------|
| `text` | string (1–2000 chars) | The natural-language request |
| `intent` | string, optional | Explicit intent; skips classification |
| `entities` | object, optional | Extracted entities |
| `source` | string | `classifier` or `explicit` |

**Plan persistence is not implemented in Day 3.** Plans are returned to the
caller and are not stored, so the two retrieval endpoints report that they
are unavailable rather than pretending otherwise.

## 11. What is not implemented

- Plan persistence and retrieval (deferred; the DB schema for runs and steps
  already exists from Day 1).
- Task execution of any kind.
- Concurrent execution. `parallel_levels` identifies candidates only.
- An LLM planning backend. The `PlanningStrategy` protocol reserves the seam.
- Tool binding. `required_capabilities` names capabilities; the Day 5
  registry resolves them to concrete registered tools.
- Plan-schema conformance scoring against the Day 3 evaluation metrics
  (`planning_quality`); the metric is defined in `evaluation_metrics.md` but
  is measured once the harness exists in Day 7.

---

**Traceability:** This component implements O2 and contribution C1 in
`research_gap.md` (structured, typed plan schema with declared dependencies
and expected outcomes). It consumes the O1 output from
`daily_checkpoints/day-2.2.md` and prepares the plan that the O4 executor
will run in Day 5 and the O5 verifier will check in Day 6.
