# Dataset and Corpus Collection Plan

**Project:** NexusAI  
**Status:** Day 1 — plan defined; **no external dataset has been collected yet**  
**Last updated:** 2026-10-20

## 1. Status of data collection — read this first

**No external dataset has been downloaded, collected, or analysed at the time
of writing.** This document defines *what is required* and *how it will be
obtained and documented*; it does not claim that any of it already exists.

Three clearly distinct categories are used throughout:

| Category | Meaning | Committed to git? |
|----------|---------|-------------------|
| **Generated fixture** | Synthesised locally by this project for testing and evaluation. No third-party source. | Yes |
| **Verified bundled dataset** | Shipped inside an installed open-source package. Provenance and licence confirmed by local inspection on 2026-10-20. | Yes (or reproducible from the package) |
| **Candidate — not yet acquired** | A public dataset identified as suitable. **Provenance and licence are NOT yet verified.** Must not be used, cited or reported as collected until verification is complete. | No |

## 2. Dataset register

### 2.1 `product_manual.md` — generated fixture

| Field | Value |
|-------|-------|
| Category | Generated fixture |
| Purpose | Document-grounded QA, retrieval, summarisation and verification scenarios (SC-01, SC-04, SC-09, SC-10, SC-12, SC-13) |
| Source | Authored locally for this project |
| Licence | Project-internal synthetic content; treated as MIT alongside the repository |
| Collection method | Hand-authored to contain a deterministic ground truth (24-month warranty, exactly 5 exclusions) |
| Expected fields | Markdown sections: Overview, Warranty (incl. 2.1 exclusions), Installation, Calibration, Operating limits, Support |
| Preprocessing | None at rest. Chunked at index time (Day 4) with a documented chunk size and overlap. |
| Privacy | None. Describes a fictional device. No real product, person or organisation. |
| Objectives | O3, O5, O6 |
| Location | `data/sample/product_manual.md` |

### 2.2 `meeting_notes.md` — generated fixture

| Field | Value |
|-------|-------|
| Category | Generated fixture |
| Purpose | Structured extraction, action-item tracking, multi-step workflow and dependency-ordering scenarios (SC-03, SC-16) |
| Source | Authored locally for this project |
| Licence | Project-internal synthetic content; treated as MIT alongside the repository |
| Collection method | Hand-authored with a deterministic action-item table (6 items, 5 named owners, one owner appearing twice) |
| Expected fields | Markdown: attendees, agenda, discussion, action-items table (#, action, owner, due), next meeting |
| Preprocessing | None at rest. Table structure must survive chunking; the Day 4 chunker must be checked against this file specifically. |
| Privacy | None. Fictional names, fictional meeting. |
| Objectives | O2, O3, O4, O6 |
| Location | `data/sample/meeting_notes.md` |

### 2.3 `sales_2026.csv` — generated fixture

| Field | Value |
|-------|-------|
| Category | Generated fixture |
| Purpose | Deterministic tabular analysis and data-analysis scenarios (SC-06, SC-11) |
| Source | Authored locally for this project |
| Licence | Project-internal synthetic content; treated as MIT alongside the repository |
| Collection method | Hand-authored; revenue column is exactly `units × unit_price` for every row so aggregates are independently checkable |
| Expected fields | `date, region, product, units, unit_price, revenue` — 26 rows, 4 regions (Northern, Southern, Eastern, Western), 3 products |
| Preprocessing | None. Loaded as a typed dataframe; `revenue` treated as float, `units` as integer. |
| Privacy | None. No real transactions. |
| Ground truth | Computed and recorded in `experiments/scenarios/SC-06-data-analysis.json` (`ground_truth` block) |
| Objectives | O2, O6 |
| Location | `data/sample/sales_2026.csv` |

### 2.4 scikit-learn bundled datasets — verified bundled dataset

| Field | Value |
|-------|-------|
| Category | Verified bundled dataset |
| Purpose | Tabular ML demonstration (classification and regression) for the Data Intelligence page and the "tabular ML demonstrations" dataset requirement |
| Source | Shipped inside the installed `scikit-learn` package (`sklearn/datasets/data/`) |
| Licence | **BSD 3-Clause** — verified by local inspection on 2026-10-20 (`scikit_learn-1.9.0.dist-info/licenses/COPYING`, and `License-Expression: BSD-3-Clause` in package metadata) |
| Collection method | Obtained by installing `scikit-learn`; no separate download, no scraping, no redistribution beyond what the package already provides |
| Available files | `iris.csv`, `wine_data.csv`, `breast_cancer.csv`, `digits.csv.gz`, `diabetes_target.csv.gz`, `diabetes_data_raw.csv.gz`, `linnerud_exercise.csv`, `linnerud_physiological.csv` |
| Expected fields | Each is a fixed, documented schema (feature columns + target column), e.g. iris: 4 numeric features + 3-class target |
| Preprocessing | Standardisation for the k-NN/linear baselines; documented per experiment |
| Privacy | These are well-known public research datasets redistributed under a permissive licence. They contain no personal data. The **Iris** dataset in particular was derived from a small taxonomic measurement study and contains no personal identifiers. |
| Objectives | O6 (supporting evidence for the tabular-ML demonstration); not used as a primary task-automation evaluation set |
| Location | Loaded via `sklearn.datasets.load_*()`; the raw CSVs are also present at `sklearn/datasets/data/` |
| Note | Not yet installed in the project virtual environment; `scikit-learn` must be added to the dependencies before use. The licence verification above was performed against the system interpreter's scikit-learn 1.9.0. |

### 2.5 Public candidate datasets — **not yet acquired, not yet verified**

The following are *candidates* only. **None has been downloaded.** Their
provenance and licences are **unverified** and must be confirmed from the
official source before any use, citation, or claim of collection.

| Candidate | Intended purpose | Verification status | Blocking issue |
|---|---|---|---|
| A public web-search result corpus (for the research/comparison scenario SC-02) | RAG and multi-step research | **Not verified** | Requires a search API or a licensed crawl corpus. The project has no paid API, so a free, licence-clear snapshot is required. |
| A public multi-hop QA dataset (e.g. HotpotQA) | Retrieval evaluation | **Not verified** | Licence and redistribution terms not yet confirmed for the specific distribution. |
| A public intent-classification dataset (e.g. CLINC150 or a banking-intents dataset) | Intent classifier training (O1) | **Not verified** | Licence and label taxonomy alignment with the NexusAI taxonomy not yet confirmed. |
| A public tabular dataset with a genuine imbalance problem | Demonstrating the "Data Intelligence" page | **Not verified** | Deferred — the scikit-learn bundled datasets (2.4) cover the Day 1–5 demonstration requirement. |

**Rule:** an entry moves from this table into §2 only after its licence and
provenance have been confirmed from the primary source, and the confirmation
date and source URL are recorded here. Until then, no result may be reported
as using that dataset.

## 3. Mapping to research objectives

| Objective | Datasets / corpus supporting it | Status |
|---|---|---|
| O1 — Intent classification | Labelled intent examples (to be authored in-project); candidate public intent datasets in §2.5 | Labelled examples not yet authored; candidates not acquired |
| O2 — Structured planning | Scenario suite + `meeting_notes.md` | Available |
| O3 — RAG over user documents | `product_manual.md`, `meeting_notes.md`; `data/raw/` reserved for user-provided documents | Sample corpus available |
| O4 — Tool execution | Scenario suite (tool registry) + `sales_2026.csv` | Available |
| O5 — Verification and recovery | Scenario suite with injected faults (SC-09 … SC-13) | Available |
| O6 — Evaluation metrics | Scenario suite + all fixtures + scikit-learn bundled datasets | Partially available |

## 4. Privacy and ethics

- **No real personal data** is collected without explicit, informed consent.
- **No user documents** are committed to the repository. `data/raw/` is
  gitignored; user-provided documents are processed locally and deleted after
  the evaluation unless retention is explicitly authorised.
- **No credentials, API keys or tokens** appear in any dataset, fixture or
  result file. `.env` is gitignored and `.env.example` contains only safe
  defaults.
- Datasets that are redistributed (the scikit-learn bundled files) retain their
  upstream licence and are obtained through the package rather than by
  re-hosting.
- Any future external dataset will be documented with its licence, source
  URL, retrieval date and checksum before use.

## 5. Reproducibility

- Every fixture in §2.1–2.3 is version-controlled, so the evaluation corpus is
  reproducible from the repository alone.
- The scikit-learn datasets are reproducible by pinning the package version in
  `pyproject.toml`.
- Scenario ground truth that is computable is stored with the scenario file
  (`ground_truth` block) rather than being recomputed from memory.
- Any dataset added later must record: source, licence, retrieval date, file
  checksum, and the exact preprocessing applied.

## 6. Directory layout

```
data/
  sample/       version-controlled generated fixtures (2.1-2.3)
  raw/          user-provided documents — gitignored, never committed
  processed/    derived artefacts — gitignored
artifacts/
  models/       trained model artefacts — gitignored
  vectors/      generated vector indexes — gitignored
experiments/
  scenarios/    version-controlled scenario definitions
  datasets/     this document
  results/      aggregated metric outputs — version-controlled
  runs/         raw execution traces — gitignored (may contain user content)
```

## 7. Outstanding work

1. Add `scikit-learn` to `pyproject.toml` dependencies and install it in the project virtual environment.
2. Author the labelled intent-classification examples for O1 (Day 2).
3. Define the intent taxonomy that the classifier and the scenarios share.
4. Resolve at least one entry from §2.5 by verifying its licence, or record
   explicitly that it was rejected and why.
5. Document the RAG chunking decision (size, overlap, strategy) once Day 4
   implementation settles it.

---

**Traceability:** This plan implements the dataset requirements of
`docs/research/data_collection_plan.md` §2 and the scenario inputs of
`docs/research/experimental_design.md` §5. Privacy rules implement the
non-negotiable project constraints on secrets and local-first operation.
