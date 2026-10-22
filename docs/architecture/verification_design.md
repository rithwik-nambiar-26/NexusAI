# NexusAI — Independent Verification: Design and Implementation Plan

**Status:** designed, not implemented. This document records what registering
`verify.content` and `verify.calculation` would take, and what the system does
today instead.

**Scope note:** this is Day 6 work. It is deliberately *not* implemented in the
current checkpoint. Nothing in this document is a claim that the verifier
exists.

---

## 1. What happens today

Every plan the planner produces ends with a verification task:

| Template | Final task | Capability |
|----------|------------|------------|
| `document_question_answering` | Verify the answer against the extracted passages | `verify.content` |
| `document_summarisation` | Verify the summary against the source | `verify.content` |
| `document_extraction` | Verify the extraction against the source | `verify.content` |
| `document_transformation` | Verify the transformation preserved content | `verify.content` |
| `data_analysis` | Verify the calculation | `verify.calculation` |

**Neither capability is registered.** The executor's behaviour is therefore
correct and is what it should be:

```
verify.content | skipped | Capability 'verify.content' is not registered
```

The task is skipped, not attempted and not completed. The execution report
records it as skipped, and the run's status reflects that a task did not
complete. The planner's `verification_criteria` string is carried on the task
and is visible in the plan and in the execution report.

**What this means for the review.** NexusAI can currently produce a wrong
answer without detecting it. The evidence is cited and checkable by a human,
but the system does not check it. This is stated in
`docs/review/KNOWN_LIMITATIONS.md` §2.1 and it is the reason Day 6 exists.

**What it must not become.** The failure mode to avoid is a "verification"
that always passes. A verifier that returns `verified` without checking
anything is worse than no verifier, because it converts an absent capability
into a false assurance. The tests in the current checkpoint assert that the
verification task is skipped, so that a future implementation has to change
those tests deliberately.

## 2. What the verifier must be given

The execution report already carries everything a verifier needs. Nothing new
has to be threaded through the executor.

| The verifier needs | It is in | Where |
|--------------------|----------|-------|
| The claims to check | The producing task's output | `ExecutionReport.task_results[].output` |
| What "correct" means for this task | The task's criteria | `Task.verification_criteria` |
| The source of truth | The document's text | The `document.read` task's output, which carries the full extracted text |
| The evidence to check claims against | The retrieval output | The `document.extract` task's output, which carries each passage with its `source_reference` |
| Which document was in scope | The plan's source | `Plan.source_document` |

The verifier runs *after* the tasks it checks, so the report contains their
outputs by the time it runs. The dependency graph already encodes this: the
verification task depends on the task it verifies.

## 3. The capability that would be registered

Two capabilities, in the same shape as every other registered tool:

### `verify.content`

**Input schema** — the claims to check and the source to check them against:

```python
class VerifyContentInput(BaseModel):
    claims: list[str]          # the statements to check
    source_text: str           # the text the claims must be supported by
    evidence: list[dict]       # the retrieved passages, with source references
    criteria: str | None       # the task's verification criteria
```

**Output schema** — the result, per claim:

```python
class VerifyContentInput(BaseModel):
    ...

class ClaimVerdict(BaseModel):
    claim: str
    supported: bool
    supporting_reference: str | None
    reason: str

class VerifyContentOutput(BaseModel):
    verified: bool             # True only when every claim is supported
    verdicts: list[ClaimVerdict]
    unsupported_claims: list[str]
    citations: list[str]
```

**Risk:** `SAFE`. Verification reads and checks; it changes nothing.

**Approval:** not required. It writes nothing.

**Where the claims come from.** The `llm.summarise` output is already
structured — `summary_text`, `sections`, `evidence` — so the claims are the
items of the sections. The `document.extract` output carries the passages with
their references.

**How a claim is checked.** A claim is supported when its content words are
present in the source text, using the same term-matching the rest of the RAG
layer already uses (`nexusai.rag.service._content_terms` and
`_matched_terms`). A claim that shares no meaningful term with the source is
reported as unsupported rather than assumed to be supported. The check is
deliberately conservative: it errs towards reporting a claim as unsupported,
because a false "verified" is the worse error.

### `verify.calculation`

**Input schema** — the computed values and the data to recompute them from:

```python
class VerifyCalculationInput(BaseModel):
    expected: dict[str, float]   # the values the task reported
    path: str                    # the dataset to recompute from
    group_by: str | None
    measure: str | None
```

**Output schema:**

```python
class VerifyCalculationOutput(BaseModel):
    verified: bool
    recomputed: dict[str, float]
    differences: list[dict]
```

**How it works.** The values are recomputed from the source file by a
different route from the one that produced them, and compared. The existing
`analyse_csv` in `nexusai/app/execution/csv_tool.py` already produces the
grouped totals; the verifier recomputes the grouping with `pandas` directly
and compares each value. A difference beyond a floating-point tolerance fails
the check.

## 4. How it plugs in

The registration is one call, in `nexusai/app/main.py`, beside
`register_document_tools` and `register_csv_tool`:

```python
register_verification_tools(tool_registry, document_service)
```

The tool module would live at `nexusai/app/execution/verification_tool.py`,
alongside `csv_tool.py` and `reminder_tool.py`, and would use the same
`ToolDefinition`, `ToolRisk.SAFE`, `RetryPolicy(max_attempts=1)` and
`idempotent=True` settings as the other read-only capabilities.

Nothing in the planner changes. The templates already name
`verify.content` and `verify.calculation`; registering the capabilities is
what makes those tasks executable.

## 5. What the executor would report

| Outcome | Task status | Run status |
|---------|-------------|------------|
| Every claim supported | `completed` | `completed` |
| A claim unsupported | `completed`, with `verified: false` in the output | `completed` — the run did what it was asked; the *answer* was wrong |
| The source could not be checked | `failed` | `failed` |

The distinction in the middle row matters. A verifier that runs and finds an
unsupported claim has *succeeded at its job*. The run is not a failure; the
answer is. Reporting the run as failed would conflate "the machinery broke"
with "the content was wrong", and would make the verification task's own
status misleading.

## 6. The work, in order

1. **The claim extractor.** A function that takes a task's output and returns
   the claims to check. For a summary, the items of its sections; for an
   extraction, the extracted values; for an answer, the sentences of the
   answer text.
2. **`verify.content`.** The input and output schemas, the handler, and the
   term-matching check. The check is conservative, as described above.
3. **`verify.calculation`.** The recomputation and the comparison.
4. **Registration.** One call in the application factory.
5. **The tests.** That a supported claim verifies, that an unsupported claim
   does not, that a fabricated claim does not verify, and that the current
   "skipped" tests are updated deliberately rather than deleted.
6. **The checkpoint.** A new daily checkpoint recording what the verifier
   found on the scenario suite, with the measured numbers.

## 7. How the verifier is evaluated

The verifier is itself measured, and the measurement is part of Day 6 rather
than Day 7. `docs/research/evaluation_metrics.md` already defines the
metrics this needs:

- **verification accuracy** — of the claims the verifier accepted, how many
  were genuinely supported;
- **unsupported-claim detection rate** — of the claims that were genuinely
  unsupported, how many the verifier caught.

Both are measured against the 18 evaluation scenarios, which carry
ground-truth labels for whether a claim is supported. The scenarios already
include `SC-12 — verification-failure`, which exists for exactly this.

A verifier that reports "verified" for a claim the ground truth marks as
unsupported is worse than no verifier, so this measurement is reported even
when it is unflattering.

## 8. What must not change

- **The planner's templates.** They already name the capabilities.
- **The executor.** No new execution path is needed.
- **The safety policy.** The verifier reads; it does not act. It must not
  require approval, because it changes nothing.
- **The literature and the comparative evaluation.** A verifier is a
  mechanism, not a result. Its accuracy is a measurement, reported with its
  support counts, alongside the conditions A/B/C comparison.
