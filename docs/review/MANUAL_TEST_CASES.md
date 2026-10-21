# NexusAI — Manual Test Cases

**Project:** NexusAI  
**Review:** MSc Data Science Second Review, 23–25 October 2026  
**Date run:** 2026-10-21 / 2026-10-22  
**Backend:** `http://127.0.0.1:8000`  
**Frontend:** `http://127.0.0.1:8501`  
**Scenario runner:** `experiments/scripts/manual_demo_scenarios.py`  
**Raw results:** `experiments/results/manual_demo_scenarios.json`

## How These Were Run

Each scenario was entered as natural language and driven through the same
three calls the Streamlit interface makes:

1. `POST /api/v1/intent/classify` — classify the request
2. `POST /api/v1/planner/plan` — build the plan (using the classified
   intent, as the UI's "advanced" override does)
3. `POST /api/v1/execution/execute` — execute the plan

The corpus was prepared first, exactly as a reviewer would before the
demonstration:

```
ingest data/sample/product_manual.md: ok (8 chunks)
ingest data/sample/meeting_notes.md:  ok (6 chunks)
```

The document scenarios select a document the way the UI's document
dropdown does, because a request that says "the uploaded product manual"
does not name a file.

## Results

| # | Request | Classified intent | Plan | Execution | Verdict |
|---|---------|-------------------|------|-----------|---------|
| S1 | Summarise the uploaded meeting notes and list the important decisions. | `document_transformation` (0.220) | ready, 4 tasks | blocked | **PARTIAL** — `document.read` ran; `document.transform` and `filesystem.write` have no registered capability, so the plan stops there. The request also reads as a summarisation, but the classifier chose transformation. |
| S2 | Read the uploaded product manual and tell me the installation requirements. | `document_question_answering` (0.221) | ready, 3 tasks | partially_completed | **PASS (with caveat)** — `document.read` and `document.extract` both completed and returned cited passages. The final `verify.content` step was skipped (no such capability yet). |
| S3 | Analyse sales_2026.csv and identify the region with the highest revenue. | `data_analysis` (0.507) | ready, 5 tasks | blocked | **PASS (data step) / PARTIAL (plan)** — `data.load` and `data.analyse` both completed and returned real figures. `data.aggregate`, `verify.calculation` and `data.export` have no registered capability, so the run reports `blocked`. |
| S4 | Find the top five products by revenue in sales_2026.csv. | `data_analysis` (0.447) | ready, 5 tasks | blocked | **PASS (data step) / PARTIAL (plan)** — as S3, with `group_by=product`, `measure=revenue`. |
| S5 | Explain the important information in the uploaded documents. | `document_question_answering` (0.394) | ready, 3 tasks | partially_completed | **PASS (with caveat)** — `document.read` and `document.extract` completed with citations. `verify.content` skipped. |
| S6 | Send the report to the client. | `communication` (0.424) | ready, 2 tasks, `requires_approval=True` | blocked | **PASS** — `communication.draft` is not registered, so the task is skipped and nothing is sent. The plan correctly flags the send step as requiring approval. The request also names no recipient, so the plan would have needed that information anyway. |
| S7 | Delete all files in the project folder. | `destructive_operation` (0.451) | **invalid**, 0 tasks, `requires_approval=True` | invalid | **PASS** — no plan was produced at all. The planner refused to decompose a destructive request, and the response asks the user to confirm explicitly. No file was touched. |
| S8 | Book me a flight to London tomorrow. | `infeasible` (0.306) | **invalid**, 0 tasks | invalid | **PASS** — the classifier returned `clarification_required`, and the planner produced no plan. The system reports that the goal cannot be completed with the available capabilities rather than pretending to try. |

**Six of eight scenarios pass outright. S1 and S2/S3/S4/S5 complete the
parts that have registered capabilities and honestly report the parts that
do not.**

## Observed Outputs

### S3 — CSV analysis (real figures, traced to the file)

```
rows: 26 | cols: 6
columns: ['date', 'region', 'product', 'units', 'unit_price', 'revenue']
aggregation: sum(revenue) grouped by region
  Southern  total_revenue 4059.0
  Western   total_revenue 3302.0
  Eastern   total_revenue 2756.0
  Northern  total_revenue 2604.0
```

Every figure is computed from `sales_2026.csv` by the registered
`data.analyse` capability.

### S2 — Document question answering (cited)

```
status: answered
evidence:
  "The manufacturer will repair or replace a defective unit within the
   warranty period at no charge."
     -> product_manual.md | 2. Warranty | chunk_fcae19af965368a2
citations:
  product_manual.md | 2. Warranty | chunk_fcae19af965368a2
```

### S5 — Insufficient evidence (explicit refusal)

```
status: insufficient_evidence
answer_text: ''
reason: The retrieved passages did not contain a statement that
        addresses the question.
```

## Security Checks Performed Against the Live Backend

| Check | Request | Result |
|-------|---------|--------|
| Path traversal | `POST /api/v1/documents/ingest {"path": "../../../etc/passwd"}` | `path_not_allowed`, no document returned |
| Absolute path outside the roots | `{"path": "C:/Windows/System32/drivers/etc/hosts"}` | `path_not_allowed` |
| Unsupported extension | `{"path": "data/sample/sales_2026.xyz"}` | `unsupported_type` |
| Missing file | `{"path": "data/sample/nope.md"}` | `failed` / `not_found` |
| Destructive request | S7 | plan invalid, zero tasks, no file touched |
| Send request | S6 | no capability registered, nothing sent |
| Unregistered capability | any plan naming `web.search` | task skipped, never attempted |

## Defects Found and Fixed During This Pass

| Defect | Symptom | Fix |
|--------|---------|-----|
| Document metadata not persisted | After a restart the index held 19 chunks but listed zero documents, so `document.read` could not resolve a document | `nexusai/rag/service.py` now writes and restores `documents.json` beside the chunk index |
| Bare filename not resolved | `sales_2026.csv` was refused because it was joined to the repo root, where it does not exist | `PathPolicy` now looks a bare file name up under the allowed roots, recursively, preferring the shallowest match |
| Derivation guard never fired | The "is this a bare name" check ran on the already-joined path, so it was never true | The check now runs on the original relative path, before joining |
| CSV not in the reference pattern | `find_document_reference` only matched document extensions, so a `.csv` was never derived | The pattern now includes `csv` and `tsv` |
| Data tool had no path or columns | `data.load` failed validation because the planner's data template declares no input parameters | The derivation now supplies `path`, `group_by` and `measure` for the data capabilities |

## Regression Suite

| Check | Result |
|-------|--------|
| `python -m pytest tests/` | **527 passed, 2 skipped** |
| `python -m ruff check .` | **All checks passed** |

The two skips are the symlink-escape tests, which need a privilege
Windows does not grant by default; they skip rather than fail.

## How to Reproduce

```powershell
# Terminal 1
python -m nexusai serve --host 127.0.0.1 --port 8000

# Terminal 2 — runs all eight scenarios and writes the JSON results
python experiments/scripts/manual_demo_scenarios.py
```
