# Execution Engine Architecture

**Project:** NexusAI  
**Document status:** Draft v0.1 — Phase 1, Day 5  
**Date:** 2026-10-21  
**Research objective:** O4 — Secure tool execution with registered tools and validated inputs

## 1. Purpose

This document specifies the controlled tool execution engine introduced in
Day 5: how a plan validated by the Day 3 planner is turned into executed
tasks, how capabilities are registered and guarded, how approval is
enforced, and how the filesystem boundary is drawn.

Four properties shape the design:

- **Nothing executes unless it is registered.** The registry is the only
  route from a capability name to a handler. There is no discovery, no
  fallback and no dynamic resolution.
- **Planning is not authorization.** A plan may declare that a task
  writes or sends; the executor is what checks the approval state and
  refuses to run it without one.
- **A failure propagates.** A task that fails blocks its dependents. A
  blocked task is never reported as completed.
- **The filesystem boundary is explicit.** Every path that reaches the
  disk passes through one policy that resolves it and checks it against
  an allowed root.

The engine executes. It does not verify the *correctness* of a result —
that is the Day 6 verifier's job, and keeping the two separate is what
makes the verification independent.

## 2. Component map

```
                    validated Plan
                         |
                         v
   +------------------------------------------------+
   |  ExecutionEngine                               |
   |  (nexusai/app/execution/engine.py)              |
   |                                                |
   |  1. plan.validate()  -> reject invalid plans  |
   |  2. dependency order and state                 |
   |  3. registry lookup    -> skip unknown tools   |
   |  4. input preparation  -> derive + validate    |
   |  5. approval check     -> block without consent |
   |  6. execute with timeout and bounded retries   |
   |  7. output validation                         |
   +----------------------+-------------------------+
                          |
          +---------------+---------------+
          |                               |
          v                               v
   +------------------+          +------------------+
   |  ToolRegistry    |          |  PathPolicy      |
   |  (registry.py)   |          |  (paths.py)       |
   |  explicit only   |          |  allowed roots   |
   +--------+---------+          +------------------+
            |
            v
   +------------------------------------------------+
   |  Registered capabilities                        |
   |  document.read | document.extract | llm.summarise|
   |  (Day 4 DocumentCapabilities)                  |
   +------------------------------------------------+
```

## 3. Tool registry

### 3.1 A tool definition

`ToolDefinition` is a frozen Pydantic model. Freezing matters: a running
execution cannot be affected by a later edit to a registered tool.

| Field | Purpose |
|-------|---------|
| `capability` | Unique capability name |
| `description` | What the tool does |
| `input_schema` | Pydantic model validating the input |
| `output_schema` | Pydantic model validating the output |
| `handler` | The callable that performs the work |
| `permissions` | Permissions the tool requires |
| `risk` | `safe`, `sensitive` or `destructive` |
| `requires_approval` | Whether explicit approval is needed |
| `timeout_seconds` | Maximum wall-clock time for one attempt |
| `retry_policy` | When and how often a failure may be retried |
| `idempotent` | Whether repeating the call has the same effect |
| `version` | Version of the definition |

### 3.2 Registration rules

* **Explicit only.** A capability becomes executable only by an explicit
  `register()` call. Nothing is discovered or auto-registered.
* **No duplicates.** Registering a capability that already exists raises
  `ToolError` with category `DUPLICATE_REGISTRATION`.
* **Unknown capabilities are refused.** `get()` on an unregistered
  capability raises `NOT_REGISTERED`. There is no fallback handler.

### 3.3 Input and output validation

`ToolRegistry.execute()` validates the payload against the tool's input
schema *before* the handler runs, and validates the handler's return value
against the output schema *after* it returns. A schema violation becomes
a structured `ToolError` — `INVALID_INPUT` or `INVALID_OUTPUT` — never a
raw exception.

An unexpected exception inside a handler is caught and reported as
`HANDLER_ERROR` with the exception type recorded, so one bad tool cannot
take the run down.

The registry has no FastAPI dependency.

## 4. Registered capabilities

Day 5 registers the three Day 4 document capabilities under exactly the
names the Day 3 planner emits in `required_capabilities`:

| Capability | Input schema | Output schema | Permissions | Approval |
|------------|--------------|---------------|-------------|----------|
| `document.read` | `DocumentReadInput` | `DocumentReadOutput` | `read_document` | No |
| `document.extract` | `DocumentExtractInput` | `DocumentExtractOutput` | `read_document` | No |
| `llm.summarise` | `LlmSummariseInput` | `LlmSummariseOutput` | `read_document` | No |

The adapters in `nexusai/app/execution/tools.py` are thin: they call the
Day 4 `DocumentCapabilities` interface and validate the result. The RAG
implementation is neither duplicated nor modified.

All three are read-only. None writes, sends or deletes, so none of them
requires approval — and binding a planner task to one of them cannot
authorise a side effect.

`DocumentReadInput` requires either a `path` or a `document_id`; the
requirement is enforced in the schema, so the failure is reported as
invalid input before the handler runs.

## 5. Input derivation

A planner task names the capability it needs, but its template may not
carry every input that capability requires. The `document.extract`
capability needs a query; `document.read` needs a path.

Rather than inventing values, the executor derives them from the plan's
own `original_request` — the text the user actually wrote:

| Capability | Derived input | Source |
|------------|---------------|--------|
| `document.read` | `path` | The first document filename referenced in the request |
| `document.extract` | `query` | The request itself |
| `llm.summarise` | `question` | The request itself |

A value the task already declares always wins. A derivation that cannot
be made leaves the input absent, so schema validation reports it. The
derivations live in `nexusai/app/execution/derivation.py` and are narrow
and explicit.

## 6. Execution lifecycle

The engine walks `plan.execution_order` and processes each task in turn.

| Stage | Behaviour |
|-------|-----------|
| Plan validation | `plan.validate()` runs first. A plan that does not validate is rejected with `INVALID` and nothing runs. |
| Duplicate check | A task already executed for this plan is skipped, not repeated. |
| Dependency check | A dependency that failed, was blocked, or was skipped for any reason other than a duplicate leaves the dependent blocked. A dependency skipped because the chain already ran leaves the dependent skipped too. |
| Capability lookup | A task with no registered capability is skipped, never attempted. |
| Risk check | A `destructive` tool is skipped. The current engine will not run one. |
| Input preparation | Declared parameters are mapped by name; missing ones are derived; the payload is validated. |
| Approval check | A tool with `requires_approval` needs a granted approval bound to the task's validated inputs. |
| Execution | The handler runs with a timeout; failures may be retried within the policy. |
| Output validation | The handler's return value is validated against the output schema. |
| Status update | The task's status is set to `COMPLETED` only when a validated output was produced. |

### Task statuses

| Status | Meaning |
|--------|---------|
| `pending` | Not yet started |
| `running` | Handler is executing |
| `completed` | Handler returned and the output validated |
| `failed` | The handler raised, timed out, or returned an invalid output |
| `blocked` | A dependency did not complete, or approval is outstanding |
| `skipped` | The capability is not registered, the tool is destructive, or the task had already run |

### Execution statuses

| Status | Meaning |
|--------|---------|
| `completed` | Every task completed, or every task was skipped because it had already run |
| `partially_completed` | Some tasks completed and others were skipped for a reason other than a duplicate |
| `failed` | A task failed and nothing else completed |
| `awaiting_approval` | A task is waiting for an approval decision |
| `blocked` | A task is blocked for a reason other than approval |
| `invalid` | The plan did not validate; nothing ran |

## 7. Approval enforcement

**Planning is not authorization.** The Day 3 planner records
`requires_approval` on a plan and `APPROVAL_REQUIRED_TASK_TYPES` marks
the task types that change state — `document_write` and
`communication_send`. Those are declarations. The executor is what
enforces them.

### 7.1 The approval request

When the engine reaches a task whose tool requires approval and no
approval exists, it:

1. computes a fingerprint of the task's validated inputs;
2. raises an `ApprovalRequest` bound to the task, the capability and
   that fingerprint;
3. leaves the task `BLOCKED` with error category `APPROVAL_REQUIRED`;
4. reports the run as `awaiting_approval`.

The dependent tasks are blocked too, because the approval-gated task has
not produced its result.

### 7.2 Binding to inputs

The fingerprint is a SHA-256 over the capability name and the validated
input payload. It is what binds an approval to a specific set of inputs:

* **Inputs unchanged** — the approval still matches and the task runs.
* **Inputs changed** — the fingerprint no longer matches, the approval is
  marked `INVALIDATED`, and the task is blocked again with error
  category `APPROVAL_INVALID`. A new approval is required.

This means an approval cannot be reused for a different operation. A
granted approval for one task does not authorise another, because each
approval is keyed by task id.

### 7.3 Approval decisions

`ExecutionEngine.approve(report, task_id, granted, note)` records a
decision against a pending request. A denied request leaves the task
`SKIPPED` — it is not an error, it is a refusal.

### 7.4 What is not implemented

No actual email sending or external communication exists. The Day 5
tool set is entirely read-only, and no write or send handler is
registered. A tool that would send or write will need a schema, a
handler and its own approval tests when it is added.

## 8. Filesystem boundary

Day 4 accepted a path supplied to the API without restricting where it
could point. Day 5 closes that.

`nexusai/app/security/paths.py` holds the one policy that decides whether
a path may be read:

| Rule | Behaviour |
|------|-----------|
| Canonicalisation | The path is resolved with `os.path.realpath`, so symlinks are followed before the check. |
| Containment | The canonical path must be inside one of the allowed roots. |
| Traversal | `..` segments are resolved away by canonicalisation and then caught by the containment check. |
| Symlink escape | A link inside a root pointing outside resolves to the outside target and is rejected. |
| Relative paths | Resolved against the project root, then checked against the roots. |
| Existence | The path must exist. |
| Regular file | A directory is not a readable document. |
| Extension | Only `.pdf`, `.docx`, `.txt`, `.text`, `.md` and `.markdown` are readable. |
| Permissions | The file must be readable. |

The containment check runs *before* the existence check, so a path outside
the roots is reported as outside the roots rather than leaking whether it
exists.

The allowed roots come from the `allowed_document_roots` setting, which
defaults to `./data`, `./docs` and `./experiments`. The document
service and the executor share one policy instance, so ingestion and
execution are governed identically.

Failure is reported, not raised: ingestion returns
`path_not_allowed`, `unsupported_format`, `corrupted`, `empty` or
`failed` as appropriate, so a caller can distinguish "not allowed" from
"not a document".

## 9. Reliability

### 9.1 Timeouts

Each tool declares `timeout_seconds`. The engine treats a `TimeoutError`
from a handler as a `TIMEOUT` failure. The timeout is enforced by the
handler's own contract — the engine does not interrupt a running
thread, because doing so is not safe. A handler that must be bounded
should implement its own timeout; the registry records the limit and
reports the breach.

### 9.2 Bounded retries

A retry policy declares `max_attempts`, `backoff_seconds` and whether a
timeout may be retried. A failure is retried only when **all** of the
following hold:

* the attempt count is below `max_attempts`;
* the tool is **idempotent**;
* the failure is a handler error, or a timeout and `retry_on_timeout` is set.

A non-idempotent tool is never retried, because repeating a write or a
send could duplicate a side effect. A `TIMEOUT` is not retried by
default, because the handler may have completed its work before the
timeout was noticed.

### 9.3 Duplicate execution protection

The engine records the tasks it has completed, keyed by plan id and task
id. Executing the same plan again skips those tasks rather than
repeating them. A task skipped this way causes its dependents to be
skipped too, because the chain has already run.

This is *not* exactly-once execution. It is an in-process guard against
repeating a side effect within one engine's lifetime. The engine holds
no durable state, so a restart loses the record. Exactly-once execution
would need a durable, transactional store, which is out of scope here.

### 9.4 Error categories

| Category | Meaning |
|----------|---------|
| `not_registered` | The capability is not in the registry |
| `duplicate_registration` | The capability was already registered |
| `invalid_input` | The payload did not satisfy the input schema |
| `invalid_output` | The handler's return value did not satisfy the output schema |
| `timeout` | The handler exceeded its time limit |
| `handler_error` | The handler raised an unexpected exception |
| `permission_denied` | The tool's risk or permissions forbid execution |
| `approval_required` | Explicit approval is outstanding |
| `approval_invalid` | The approval no longer matches the inputs |
| `path_not_allowed` | The path is outside the allowed roots |
| `skipped` | The task was skipped, including duplicate runs |
| `blocked` | A dependency did not complete |

### 9.5 Logging

Every registration, execution and failure is logged through the project's
existing structured logger, with the capability, the execution id and
the elapsed time. Request ids correlate the log lines with the HTTP
request.

## 10. API surface

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v1/execution/execute` | Execute a plan and return the report |
| POST | `/api/v1/execution/approve` | Record an approval decision |
| GET | `/api/v1/execution/tools` | List the registered capabilities |
| GET | `/api/v1/execution/status` | Report engine availability |

**Execution history is not persisted.** The report is returned in the
response and the last report is held on the application state in memory
so the approval endpoint can act on it. A restart loses it. The
endpoints say so rather than implying a durable history; persisting
executions is Day 7 work alongside the experiment harness.

The service layer has no FastAPI dependency. The registry and the engine
can be driven from the CLI, the UI or the experiment harness.

## 11. What is not implemented

- A write or send tool. No handler that modifies state or contacts an
  external service exists, so the approval path is exercised by tests
  rather than by a live side effect.
- Durable execution history or exactly-once execution.
- Per-tool resource isolation: a handler runs in the calling process
  with the application's own permissions.
- Cancellation of a running execution.
- Concurrency. Tasks run sequentially in dependency order; the planner's
  `parallel_levels` are not used.
- Verification of a result's correctness — that is the Day 6 verifier.
- Adaptive replanning after a failure — that is the Day 6 replanner.

---

**Traceability:** This component implements O4 and contributes to C4 in
`research_gap.md` (registered tool set with input-schema validation and
user approval gates). It consumes the plan produced by the Day 3
planner and the capabilities produced by the Day 4 document module, and
it provides the execution evidence that the Day 6 verifier will check
and that the `tool-selection accuracy` and `invalid-invocation rate`
metrics in `evaluation_metrics.md` will be computed from.
