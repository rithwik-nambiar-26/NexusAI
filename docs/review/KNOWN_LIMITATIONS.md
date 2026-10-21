# NexusAI — Known Limitations

**Project:** NexusAI  
**Review:** MSc Data Science Second Review, 23–25 October 2026  
**Date:** 2026-10-22

This document states what NexusAI does not do. Everything here is
verified against the actual implementation, not inferred from intent.

## 1. Research Limitations

### 1.1 The comparative evaluation has not been run

The central claim of the project — that a hybrid architecture is more
reliable than a rule-based or LLM-only baseline — **has not been
tested**. Conditions A and B do not exist as code. The test matrix, the
scenario suite, the metrics and the analysis plan are all defined in
`docs/research/`; the experiment that would produce results is Day 7
work.

**Consequence:** no comparative claim can be made at the review. Any
statement that the hybrid approach outperforms a baseline would be
unsupported.

### 1.2 The literature is unverified

All 26 entries in `docs/research/literature_matrix.md` are marked
`REQUIRES EXTERNAL VERIFICATION`. Title, authors, year, venue, DOI and
the characterisation of each finding still need to be checked against
the primary source.

**Consequence:** the literature review can be presented as a structured,
well-mapped synthesis, but not as a verified one.

### 1.3 The intent classifier is experimental

| Property | Value |
|----------|-------|
| Training examples | 75 (19 scenario-derived, 56 authored) |
| Classes | 12 |
| Held-out test set | 15 examples |
| Test accuracy | 0.667 |
| Test macro F1 | 0.622 |
| Per-class F1 of 0.00 | `data_analysis`, `destructive_operation`, `infeasible` |
| Probability calibration | Not performed |

With 15 test examples spread over 12 classes, most per-class metrics
rest on a single example. The macro F1 is a rough indicator, not a
precise measurement.

**Consequence:** the classifier is used as a *proposal* that the planner
and executor treat sceptically. Its confidence is recorded but never
relied upon for safety. The two classes that score 0.00 are among the
refusal paths, where the current behaviour errs towards asking rather
than acting.

### 1.4 The dataset is small and entirely synthetic

No real user data was collected. Every example is either derived from a
synthetic evaluation scenario or authored by hand. Generalisation to
real phrasing is untested.

## 2. Functional Limitations

### 2.1 Independent verification is not implemented

Every generated plan ends with a verification task — `verify.content` or
`verify.calculation` — but no such capability is registered. Those tasks
are reported as **skipped**.

**Consequence:** NexusAI can currently produce a wrong answer without
detecting it. The evidence is cited and checkable by a human, but the
system does not check it. This is Day 6.

### 2.2 Adaptive replanning is not implemented

A failed task blocks its dependents and the run ends. Nothing revises
the plan and retries. Day 6.

### 2.3 No capability writes, sends or deletes

The registered capabilities are:

| Capability | Reads | Writes | Sends |
|-----------|:-----:|:------:|:-----:|
| `document.read` | ✅ | — | — |
| `document.extract` | ✅ | — | — |
| `llm.summarise` | ✅ | — | — |
| `data.load` | ✅ | — | — |
| `data.analyse` | ✅ | — | — |

**Consequence:** "send the report to the client" and "delete all files"
are both correctly refused — but because no capability exists, not
because an approval gate refused them. The approval *mechanism* is
implemented and tested (Day 5, `tests/unit/execution/test_engine.py`);
it has no live state-changing tool to act on yet.

### 2.4 The planner's templates are one shape per intent

Each intent has a single canonical task chain. A request that fits the
intent but needs a different shape still gets the standard chain. For
example, the `data_analysis` template has five steps, but only
`data.load` and `data.analyse` have implementations; the remaining three
are skipped.

**Consequence:** plans describe a reasonable workflow, not a bespoke one.
Request-specific variation is carried in task parameters, not in task
structure.

### 2.5 Execution history is not persisted in full

What is persisted in SQLite, per run: the request, the classified
intent, the run status and the plan.

What is not persisted: the per-task output, the per-task timing and the
approval record. The execution report is returned in the HTTP response
and held in memory only.

**Consequence:** the Run History page shows what ran and how it ended,
but not the full output of a past run.

### 2.6 The duplicate-execution guard is in-process

A task already executed for a plan is skipped on a second execution of
that plan, within one engine's lifetime. The guard is lost on restart.

**Consequence:** this is *not* exactly-once execution. The Day 5
architecture document states this explicitly. A durable, transactional
guard would need a different store.

### 2.7 Timeouts are declarative

Each tool declares a `timeout_seconds`. A handler that raises
`TimeoutError` is reported as a timeout. The engine does **not**
interrupt a running thread, because doing so is not safe in-process.

**Consequence:** a handler that hangs will hang. A handler that must be
bounded should enforce its own timeout.

### 2.8 Any handler exception is treated as potentially transient

A failed attempt is retried up to the policy limit when the tool is
idempotent. The `idempotent` flag is the lever to prevent a retry, and
every registered tool currently sets it to `True` — correctly, because
they are all read-only.

**Consequence:** a read-only tool whose failure is permanent will be
retried before giving up. Harmless for the current tool set, but worth
noting for future write-capable tools.

### 2.9 Answers are extractive, not generative

Answers and summaries are assembled from sentences in the source text.
No new prose is generated.

**Consequence:** every claim is checkable, but the output is less fluent
than a generated answer. A generative backend could be added behind the
same service interface; none exists.

### 2.10 Retrieval is lexical by default

The default embedder is a deterministic hashing embedder that matches on
word overlap. The Sentence Transformers embedder matches semantically and
is available, but needs the model present locally.

**Consequence:** a question phrased differently from the document may
retrieve weakly. The IDF weighting and the prefix-matched stemming
mitigate this but do not remove it.

### 2.11 No web sources

The `research` template names `web.search` and `web.fetch`, but no such
capability is registered. A research request retrieves from the local
corpus only.

**Consequence:** "heterogeneous **real-time** information" in the research
question is currently limited to local documents. This matters for the
research framing, not just the implementation.

### 2.12 PDF parsing is text-only

Text is extracted in page order. Tables are read as text. There is no OCR
for scanned documents, and no layout-aware parsing.

## 3. Interface Limitations

### 3.1 The UI needs the backend running

Every page checks the backend's reachability and shows a clear message
when it is down. The UI never shows invented data — but a reviewer
cannot explore it without starting the server.

### 3.2 A request that says "the document" needs the document chosen

With more than one document indexed, the planner will not guess. The
Task Automation page provides a document dropdown; the API caller must
supply a `document_id` or a path. A single request naming a file
(`data/sample/product_manual.md`) works without any selection.

### 3.3 The intent override is visible but not the default

The Task Automation page has an "Advanced" panel to supply an explicit
intent. The default path uses the classifier. Both are recorded in the
plan's `source` field, so a reviewer can tell which was used.

## 4. Security Boundaries

Stated plainly, because these are deliberate and should be presented as
design decisions rather than gaps.

| Boundary | Current state |
|----------|---------------|
| Filesystem reads | Restricted to configured roots (`./data`, `./docs`, `./experiments` by default). Canonical resolution defeats traversal and symlink escapes. |
| Path policy | Shared by ingestion and execution, so they cannot diverge. |
| Arbitrary code execution | **None.** No `eval`, `exec`, `subprocess` or shell access anywhere in the application. |
| Model-generated instructions | Documents are data, never instructions. Nothing in a document is executed or obeyed. |
| Tool execution | Only explicitly registered capabilities, with schema-validated input and output. |
| Destructive tools | Skipped outright; none is registered. |
| Approval | Enforced by the executor, bound to the task's validated inputs. |
| Secrets | No credentials, environment variables or `.env` values are exposed to the UI. |

**Known gap:** the document API reads a caller-supplied path under the
allowed roots. A caller who can reach the API can read any file under
those roots. Restricting reads to a per-user area is not implemented;
today the roots are the boundary.

## 5. Engineering Limitations

- **No linter configuration beyond Ruff** for imports, style and
  bugbears. There is no type checker in the pipeline.
- **No CI workflow** is configured, despite `workflow` being a granted
  token scope. The test suite has been run manually throughout.
- **Coverage is not measured** in CI. The `pytest-cov` configuration
  exists in `pyproject.toml` but the report is not enforced.
- **The `.venv` is not fully provisioned.** It was missing
  scikit-learn, PyMuPDF and python-docx, which were installed during
  Day 5.5. A fresh clone needs `pip install -e .[dev]`.
- **The Sentence Transformers model is a local cache, not a
  dependency.** A fresh clone will not have it, and the default
  hashing embedder is used instead. This is intentional — it keeps the
  pipeline testable offline — but it means embedding quality differs
  between machines.

## 6. Scope Boundaries (Deliberate, Not Gaps)

- No multi-user collaboration
- No production web or mobile frontend
- No paid API, paid database or AWS dependency
- No safety-critical, medical, legal or regulated financial automation
- No foundation-model training

These are stated in `docs/architecture/system_overview.md` §6 and were
agreed at project level.

## 7. Highest-Risk Limitations for the Review

| # | Limitation | Risk | Mitigation |
|---|------------|------|------------|
| 1 | The comparative A/B/C evaluation has not been run | **High** | Days 6 and 7. The design, scenarios, metrics and rubric are complete; only the execution is missing. |
| 2 | The literature is unverified | **High** | Independent of Days 6–7; can be worked on in parallel. |
| 3 | No independent verification, so a wrong answer is undetectable | Medium | Day 6. The execution report already carries the evidence a verifier needs. |
| 4 | Only 5 read-only capabilities exist, so "sending" and "deleting" are refused for lack of a tool rather than by policy | Medium | Present it accurately: the approval mechanism is implemented and tested, but has no live write-capable tool to act on. |
| 5 | The classifier is weak on three classes | Medium | The weak classes are refusal paths, where the current behaviour is safest. |
| 6 | The dataset is small and synthetic | Medium | Stated throughout the evaluation documentation; the metrics are reported with their support counts. |

---

**Nothing in this document describes work that was not inspected.** Where
a limitation is stated, the corresponding code path was read or the
behaviour was observed in a live run.
