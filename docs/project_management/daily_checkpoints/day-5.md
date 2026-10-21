# Day 5 checkpoint — 2026-10-21 (Controlled Tool Execution Engine)

**Day 5 objective:** Controlled tool execution engine (O4).
**Starting commit:** `7d8cc5d`
**Day 3 review:** approved. Its findings are carried forward in §10.

## 1. Completed

- **Filesystem access policy** (`nexusai/app/security/paths.py`): the single
  place that decides whether a path may be read. Canonicalises with
  `os.path.realpath` (so symlinks are followed before the check), requires
  containment in an allowed root, rejects `..` traversal and symlink
  escapes, and enforces existence, regular-file, extension and
  readability. The containment check runs before the existence check so
  an out-of-root path does not leak whether it exists.

- **Configuration** (`nexusai/app/config.py`): new `allowed_document_roots`
  setting, defaulting to `./data`, `./docs` and `./experiments`.

- **Policy applied to the Day 4 service** (`nexusai/rag/service.py`): the
  document service now takes a `path_policy`; ingestion refuses a path
  outside the roots and reports the precise reason
  (`path_not_allowed`, `unsupported_format`, `corrupted`, `empty`,
  `failed`) rather than a single generic error.

- **Typed tool registry** (`nexusai/app/execution/registry.py`):
  `ToolDefinition` (frozen Pydantic model) carrying capability, description,
  input schema, output schema, handler, permissions, risk, approval
  requirement, timeout, retry policy and idempotency. Explicit
  registration only; duplicate registration rejected; unknown
  capabilities refused; inputs validated before the handler runs and
  outputs validated after; handler exceptions converted to structured
  errors.

- **Day 4 capability adapters** (`nexusai/app/execution/tools.py`): the
  three document capabilities registered under exactly the names the Day 3
  planner emits — `document.read`, `document.extract`, `llm.summarise` —
  with Pydantic input and output schemas. The adapters call the existing
  Day 4 `DocumentCapabilities` interface; the RAG implementation is
  neither duplicated nor modified.

- **Input derivation** (`nexusai/app/execution/derivation.py`): narrow,
  explicit derivations of the inputs a capability needs from the plan's
  own `original_request` — a document path for `document.read`, the
  request as the query for `document.extract` and the question for
  `llm.summarise`. A declared value always wins; an underivable value is
  left absent so schema validation reports it.

- **Execution engine** (`nexusai/app/execution/engine.py`): the execution
  lifecycle, dependency handling, duplicate-execution protection, timeouts,
  bounded retries, error categories and the overall execution report.

- **Approval model**: an approval request is bound to a SHA-256
  fingerprint of the task's validated inputs. Changing the inputs
  invalidates the approval; the task is blocked again. The executor
  enforces the approval, not the planner.

- **API** (`nexusai/app/api/routes/execution.py`,
  `nexusai/app/api/schemas/execution.py`): four endpoints under
  `/api/v1/execution`. The registry and engine are application-scoped.

## 2. Objectives Advanced

- **O4** — Secure tool execution with validation: **IMPLEMENTED**
  - Explicit registry; nothing executes unless registered
  - Input and output schema validation
  - Approval enforced by the executor and bound to the task's inputs
  - Dependency-ordered execution with failure propagation
  - Filesystem access restricted to configured roots
  - Tool-selection accuracy and invalid-invocation rate are *defined* in
    `evaluation_metrics.md` but not yet *measured*; the measurement
    harness is Day 7 work

## 3. Metric Results (Preliminary)

| Metric | Value | Evidence |
|--------|-------|----------|
| Tests passing | 526/526 | `python -m pytest tests/` |
| Ruff lint | Clean | `python -m ruff check .` |
| New Day 5 tests | 87 | 60 unit (`tests/unit/execution/`, `tests/unit/security/`), 12 integration, 15 added across existing suites |
| Registered capabilities | 3 | `document.read`, `document.extract`, `llm.summarise` |
| Capabilities required by a document plan, satisfied | 3 / 3 | `test_capability_names_match_the_planner` |
| Tools requiring approval | 0 (all read-only) | `test_tools_are_read_only` |
| Traversal attempts refused | All | `test_traversal_is_rejected`, `test_document_api_path_traversal_is_refused` |
| Symlink escapes refused | Yes (test skipped where the OS forbids symlinks) | `test_symlink_escape_is_rejected` |
| Tool-selection accuracy | Not yet measured | Requires the Day 7 harness |
| Invalid-invocation rate | Not yet measured | Requires the Day 7 harness |

## 4. Verification Evidence

### End-to-end execution (executed)

```
ingest data/sample/product_manual.md  -> ok, 8 chunks

POST /api/v1/execution/execute
  plan: "Read data/sample/product_manual.md and summarise the warranty conditions."
        intent=document_summarisation

  status: partially_completed
    document.read    : completed
    document.extract : completed
    llm.summarise   : completed
    verify.content   : skipped   (not registered — Day 6)

  summary citations:
    product_manual.md | 2.1 Warranty exclusions | chunk_7b6da0a3f8161499
    product_manual.md | 1. Overview | chunk_5e69a8b57e85a3a4
```

The `verify.content` task is correctly **skipped** rather than failed: it
belongs to the Day 6 verifier, which is deliberately a separate component.

### Path security (executed)

```
policy roots: [D:/NexusAI/data, D:/NexusAI/docs, D:/NexusAI/experiments, <tmp>]
  valid              -> allowed
  traversal ..       -> outside_root
  absolute outside   -> outside_root
  nonexistent        -> not_found
  existing bad ext   -> unsupported_type
  directory          -> not_readable
  symlink escape     -> outside_root   (test skipped where the OS forbids symlinks)

API: POST /api/v1/documents/ingest {"path": "../../../etc/passwd"}
  -> status: path_not_allowed, document: null
```

### Approval binding (executed)

```
first execution  -> task blocked, run status awaiting_approval, approval pending
approve(task, granted=True)
second execution -> task completed          (inputs unchanged)
inputs changed   -> task blocked, approval invalidated, error category approval_invalid
```

### Duplicate execution (executed)

```
first execution  -> 3 tasks completed
second execution -> all tasks skipped ("already been executed"), run status completed
```

## 5. Safety and Approval Handling

| Concern | Handling |
|---------|----------|
| Unknown capability | Skipped, never attempted. The registry is the only route to a handler. |
| Duplicate registration | Rejected with `DUPLICATE_REGISTRATION`. |
| Invalid input | Rejected by the input schema before the handler runs. |
| Invalid output | Rejected by the output schema after the handler returns. |
| Approval not given | Task is blocked, run is `awaiting_approval`, dependents blocked. |
| Approval granted, inputs changed | Approval invalidated; task blocked again with `approval_invalid`. |
| Approval for another task | Does not apply — approvals are keyed by task id. |
| Destructive tool | Skipped. The engine will not run one. |
| Failed dependency | Dependent is blocked, never run. |
| Failed task | Never reported as completed. |
| Path outside the roots | Refused with `path_not_allowed`. |
| Traversal / symlink escape | Refused; the canonical path is checked, not the written one. |
| LLM-generated instructions | Not executable. The engine resolves a capability name to a registered handler; it never interprets text as a command. |
| `eval` / `exec` / shell | Not present anywhere in the execution subsystem. |
| Non-idempotent tool | Never retried. |
| Side effects | None exist: every registered tool is read-only. |

## 6. Known Limitations

1. **No state-changing tool exists.** The approval path is implemented and
   tested, but every registered capability is read-only. A write or send
   handler still needs a schema, a handler and its own approval tests.
2. **Execution history is not persisted.** The report is returned in the
   response and the last report is held in memory. A restart loses it.
   The API says so rather than implying a durable history.
3. **Duplicate protection is in-process, not exactly-once.** The guard
   prevents repeating a side effect within one engine's lifetime; it does
   not survive a restart.
4. **Timeouts are declarative.** The registry records a limit and reports
   a `TimeoutError` as a timeout, but the engine does not interrupt a
   running thread. A handler that must be bounded should implement its own
   timeout.
5. **A transient handler error is retried.** Any handler exception is
   treated as potentially transient and retried up to the policy limit.
   A handler that raises for a permanent reason will be retried too; the
   tool's `idempotent` flag is the lever to prevent that.
6. **Tasks run sequentially.** The planner's `parallel_levels` are not
   used, and there is no cancellation.
7. **No per-tool isolation.** A handler runs in the calling process with
   the application's own permissions.
8. **Path restriction is by configuration.** A legitimate file outside
   the configured roots is refused; the roots must be set to suit the
   deployment.
9. **Tool-selection accuracy is not measured.** The definition exists in
   `evaluation_metrics.md`; the measurement needs the Day 7 harness.

## 7. Blocker(s)

- None blocking Day 5 completion.

## 8. Definition of Done Met?

**Yes** for the Day 5 scope:

- Configurable allowed document root, canonical resolution, traversal and
  symlink protection ✅
- Typed, extensible registry with explicit registration ✅
- Day 4 capabilities registered under the planner's names ✅
- Execution engine with dependency ordering, validation and reporting ✅
- Approval enforced by the executor and bound to task inputs ✅
- Timeouts, bounded retries, structured errors and logging ✅
- API integration ✅
- Comprehensive tests ✅
- Documentation ✅

## 9. Git

- Commit message: `feat(execution): implement controlled tool execution engine`
- Commit hash: (recorded after commit creation)
- Working tree: clean after commit

## 10. Day 3 Review Findings Carried Forward

| Review requirement | How Day 5 honours it |
|--------------------|----------------------|
| The intent classifier is experimental with weak per-class performance | Day 5 does not depend on the classifier. The execution tests supply explicit intents and explicit plans. The Day 2 limitations are unchanged. |
| Explicit intent overrides must remain available | Unchanged. The planner's `intent` parameter and the `source` field are untouched. |
| Classification confidence and source must remain traceable | Unchanged. `source` still records `classifier` or `explicit`. |
| Planning is not authorization | Enforced structurally: the executor checks the approval state and refuses to run an approval-gated task, regardless of what the plan says. |
| Sending and writing require explicit approval at execution time | The approval check lives in the executor, not the planner. A plan declaring `document_write` or `communication_send` is blocked until an approval bound to the task's inputs is granted. |
| Destructive operations stay blocked | The engine skips any tool classified as destructive, and no destructive capability is registered. |
| Do not claim planning quality is measured | The checkpoint claims no planning-quality, tool-selection-accuracy or invalid-invocation-rate figure. All are marked "not yet measured; requires the Day 7 harness". |

## 11. Day 6 Dependencies

Day 6 (independent verifier and bounded replanner) depends on Day 5 in
these ways:

- The verifier must check a task's output. The execution report carries
  each task's validated output and the `error` that stopped it, so the
  verifier has what it needs without re-running anything.
- The verifier must be independent of the executor, exactly as the
  executor is independent of the planner. The registry's per-tool
  `output_schema` gives a typed contract to check against.
- The replanner will need to re-run a task after a change. The engine's
  duplicate-execution guard would skip a task that already ran, so the
  replanner needs a way to clear that state for the task it revises.
  `ExecutionEngine.reset()` clears it wholesale; a per-task reset would
  be needed for a targeted re-run.
- The `verify.content` capability that the planner's document workflows
  require is not yet registered. It is the Day 6 verifier's natural
  home, and registering it is part of that day.

---

**Conclusion:** Day 5 is complete. NexusAI can now execute a validated
plan through an explicit tool registry, with input and output schema
validation, dependency-ordered execution, approval enforced by the
executor and bound to the task's inputs, bounded retries, and a
filesystem boundary that defeats traversal and symlink escapes. The
registered capabilities are the three read-only document operations, so
no side effect is possible yet. Execution accuracy has not been
measured; that requires the Day 7 harness. Day 6 may begin after review.
