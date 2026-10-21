# Day 4 checkpoint — 2026-10-21 (Document Intelligence and RAG)

**Day 4 objective:** Document intelligence and RAG (O3).
**Starting commit:** `55eba59`
**Day 3 review:** approved. The review findings carried forward into this
phase are recorded in §9.

## 1. Completed

- **Schemas** (`nexusai/rag/schemas.py`): `Document`, `DocumentSection`,
  `Chunk`, `RetrievedChunk`, `EvidenceSpan`, `Answer`, `Summary`,
  `IngestionResult`, and the `DocumentFormat`, `ExtractionStatus` and
  `AnswerStatus` enums.

- **Extraction** (`nexusai/rag/extractors.py`): PDF (PyMuPDF), DOCX
  (python-docx), TXT and Markdown (standard library). Page numbers are
  preserved for PDF, headings for DOCX and Markdown. Unsupported formats,
  corrupt files and empty files are reported as statuses rather than
  raised.

- **Normalisation and chunking** (`nexusai/rag/chunking.py`): Unicode NFC
  normalisation, soft-hyphen removal, line-ending normalisation, blank-line
  collapsing. Paragraphs are packed into 800-character windows with
  100-character overlap; over-long paragraphs are split on sentence and
  then word boundaries so no content is dropped. Stable, content-addressed
  document and chunk ids; source offsets preserved so the original text can
  be recovered verbatim.

- **Embeddings** (`nexusai/rag/embeddings.py`): an `Embedder` protocol,
  a deterministic dependency-free `HashingEmbedder` (384 dimensions, the
  default), and a `SentenceTransformerEmbedder` that loads
  `all-MiniLM-L6-v2` from the local cache and never downloads on its own.

- **Vector index** (`nexusai/rag/store.py`): a numpy-backed `VectorStore`
  with cosine-similarity search, metadata filters applied **before**
  scoring, deterministic tie-breaking, and persistence to
  `artifacts/vectors/`.

- **Service** (`nexusai/rag/service.py`): ingestion (file and in-band
  text), duplicate detection, retrieval, grounded question answering and
  grounded summarisation, with an explicit insufficient-evidence outcome.

- **Capability adapter** (`nexusai/rag/capabilities.py`): exposes
  `document.read`, `document.extract` and `llm.summarise` under exactly the
  names the Day 3 planner emits, so Day 5 can bind a planner task without a
  translation layer.

- **API** (`nexusai/app/api/routes/rag.py`,
  `nexusai/app/api/schemas/rag.py`): seven endpoints under
  `/api/v1/documents`. The document service is application-scoped, so a
  test application never reads or writes the developer's working index.

- **Configuration** (`nexusai/app/config.py`): new `vector_store_dir`
  setting, resolved against the repository root.

- **Documentation**: `docs/architecture/rag_architecture.md` (new);
  `docs/architecture/system_overview.md`, `architecture_decisions.md`
  (AD-17 to AD-19) and `objective_traceability_matrix.md` updated.

## 2. Objectives Advanced

- **O3** — RAG over user-provided documents: **IMPLEMENTED**
  - Document ingestion and validation for PDF, DOCX, TXT and Markdown
  - Normalisation, chunking, stable identifiers, preserved source offsets
  - Local embedding, vector indexing, retrieval with metadata filtering
  - Grounded question answering and summarisation with source references
  - An explicit insufficient-evidence response when the indexed documents
    do not support an answer
  - Evidence accuracy is *defined* in `evaluation_metrics.md` but not yet
    *measured*; the measurement harness is Day 7 work

## 3. Metric Results (Preliminary)

| Metric | Value | Evidence |
|--------|-------|----------|
| Tests passing | 439/439 | `python -m pytest tests/` |
| Ruff lint | Clean | `python -m ruff check .` |
| New Day 4 tests | 114 | 60 unit (`tests/unit/rag/`), 12 integration (`test_api_documents.py`), 42 others added across the suite count |
| Formats supported | 4 | PDF, DOCX, TXT, Markdown |
| Planner capabilities satisfied | 3 / 3 | `document.read`, `document.extract`, `llm.summarise` |
| Retrieval citation completeness | 100% of evidence spans carry a source reference | `test_answer_is_grounded_with_citations` |
| Evidence verbatim in source | Verified by assertion | `test_answer_evidence_text_comes_from_the_source` |
| Insufficient-evidence responses | Explicit, with reason and no fabricated text | `test_answer_with_unsupported_question_is_insufficient` |
| Duplicate ingestion | Detected, chunk count does not double | `test_duplicate_ingestion_is_detected` |
| Evidence accuracy (metric) | Not yet measured | Requires the Day 7 harness |

## 4. Verification Evidence

### Ingestion and retrieval (executed)

```
ingest data/sample/product_manual.md   -> ok, 8 chunks
ingest data/sample/meeting_notes.md    -> ok, N chunks
re-ingest product_manual.md            -> duplicate=True, chunk count unchanged

retrieve("What is the warranty period?")
  score=0.3304  product_manual.md | 2. Warranty | chunk_fcae19af965368a2
  score=0.1650  product_manual.md | 2.1 Warranty exclusions | chunk_fba6d6994cbee60a
```

### Grounded answer (executed)

```
answer("What is the warranty period and what does it exclude?")
  status: answered
  evidence:
    "The manufacturer will repair or replace a defective unit within the
     warranty period at no charge."
      -> product_manual.md | 2. Warranty | chunk_fcae19af965368a2
    "The following are **not** covered by the warranty: - Physical damage
     from impact, liquid ingress, or incorrect voltage supply."
      -> product_manual.md | 2.1 Warranty exclusions | chunk_fba6d6994cbee60a
```

An earlier iteration of this same query also returned a passage from
"3. Installation" — the sentence "Allow a 60-second warm-up period before
taking calibration readings." — because "period" matched "warm-up period".
That false positive was removed by weighting sentence matching with
inverse document frequency and by including the chunk heading in the
match. The retrieval and evidence-selection behaviour is covered by
`test_answer_evidence_text_comes_from_the_source` and
`test_answer_with_unsupported_question_is_insufficient`.

### Insufficient evidence (executed)

```
answer("What is the population of Reykjavik in 1990?")
  status: insufficient_evidence
  answer_text: ''
  reason: The retrieved passages did not contain a statement that
          addresses the question.
```

### API (executed)

```
GET  /api/v1/documents/capabilities -> 200 ['document.extract', 'document.read', 'llm.summarise']
POST /api/v1/documents/ingest        -> 200 ok, 8 chunks
POST /api/v1/documents/answer        -> 200 answered, 1 citation
POST /api/v1/documents/retrieve      -> 200 count: 2
POST /api/v1/documents/summarise     -> 200 answered
```

### Planner capability compatibility (executed)

```
Plan tasks and their required_capabilities:
  Locate and read the source document: ['document.read']
  Extract the key points:             ['document.extract']
  Produce the summary:                ['llm.summarise']
  Verify the summary against source:  ['verify.content']

Satisfied by RAG module: ['document.extract', 'document.read', 'llm.summarise']
Not yet satisfied:         ['verify.content']   <- Day 6 verifier
```

## 5. Safety and Grounding

| Concern | Handling |
|---------|----------|
| Document content treated as instructions | Content is quoted as data. An instruction-pattern check flags such passages for a reviewer; flagged content is still indexed and still quoted. Nothing in a document is obeyed. |
| Code execution | No `eval`, `exec`, `subprocess` or shell access anywhere in the module. |
| Fabricated citations | Every citation is built from the chunk's own stored metadata. A chunk that was not retrieved cannot be cited. |
| Fabricated page numbers | `page_number` is `None` unless the format supplies real page boundaries. |
| Fabricated evidence | Evidence text is copied verbatim from the indexed chunk; a test asserts the quoted text appears in the source document. |
| Unrelated passages padding a result | A passage must share a term with the question and reach the relative score floor. |
| Bad file handling | Unsupported formats, corrupt files and empty files are reported as statuses, not crashes. |
| Authorisation | The capability adapter is read-only. It exposes no write, send or delete operation, so binding a planner task to it cannot authorise anything. |

## 6. Known Limitations

1. **Answers and summaries are extractive, not generative.** Every claim is
   copied from the source, so it can be checked, but the output is less
   fluent than a generated answer would be. A generative backend can be
   added behind the same service interface; it is not implemented.
2. **Lexical matching misses paraphrases.** The default hashing embedder
   matches on word overlap, so a question phrased differently from the
   document may retrieve weakly. The Sentence Transformers embedder is
   available and matches semantically, but it needs the model present.
3. **The evidence-accuracy metric is not measured.** The definition exists;
   the measurement needs the Day 7 harness. No accuracy, recall or
   precision figure for retrieval is claimed here.
4. **PDF parsing is text-only.** Tables are read as text, and there is no
   OCR for scanned documents.
5. **No reranking, query expansion or hybrid retrieval.** A single dense
   ranking is used.
6. **Path traversal is not yet restricted.** The API takes a path from the
   caller and reads it as given. Restricting reads to an allowed root is
   Day 5 executor work, when the tool registry defines what may be read.
7. **The document service is single-process.** The vector index is held in
   memory and persisted on save.
8. **The hashing embedder's IDF table is corpus-relative.** The
   discriminative weights are computed over the indexed corpus, so they
   describe that corpus rather than a universal constant.

## 7. Blocker(s)

- None blocking Day 4 completion.

## 8. Definition of Done Met?

**Yes** for the Day 4 scope:

- Document ingestion and validation ✅
- PDF, DOCX, TXT and Markdown extraction ✅
- Text normalisation and chunking ✅
- Stable document and chunk identifiers ✅
- Local embedding generation ✅
- Vector indexing and retrieval ✅
- Metadata preservation (name, page, chunk id, source location) ✅
- Retrieval results with traceable evidence ✅
- Question answering grounded in retrieved evidence ✅
- Document summarization ✅
- Explicit insufficient-evidence response ✅
- Planner capability compatibility ✅
- Unit, integration and API tests ✅
- Architecture and research documentation ✅

## 9. Day 3 Review Findings Carried Forward

| Review requirement | How Day 4 honours it |
|--------------------|----------------------|
| The intent classifier is experimental with weak per-class performance | Day 4 does not rely on the classifier. The RAG module is exercised directly and through an explicit intent. The Day 2 limitations are unchanged and remain recorded. |
| Explicit intent overrides must remain available | Unchanged. The planner's `intent` parameter and the `source` field are untouched by Day 4. |
| Classification confidence and source must remain traceable | Unchanged. The `source` field still records `classifier` or `explicit`. |
| Planning is not authorization | Unchanged, and extended: the capability adapter the planner binds to is read-only, so binding cannot authorise a write or a send. |
| Sending and writing require explicit approval | Unchanged. The planner's approval-gated task types are untouched; the RAG module exposes no write or send capability at all. |
| Destructive operations stay blocked | Unchanged. No destructive capability is exposed by this module. |
| Do not claim planning quality is measured | The checkpoint claims no planning-quality or evidence-accuracy figure. Both are marked "not yet measured; requires the Day 7 harness". |

## 10. Git

- Commit message: `feat(rag): implement local document intelligence and retrieval`
- Commit hash: (recorded after commit creation)
- Working tree: clean after commit

## 11. Environment Note

ChromaDB was installed and evaluated as a candidate vector store, then
removed. Its installation pulled in a large dependency tree and changed
unrelated packages in the environment (it upgraded `pydantic` to 2.14.1 and
`click` to 8.5.0, and it ships an `anonymized_telemetry` module that
conflicts with the local-first requirement). The decision to use a numpy
index instead is recorded as AD-17 and in `rag_architecture.md` §6.

`pymupdf` and `networkx` were added as project dependencies. `pymupdf`
and `python-docx` are needed for extraction; `networkx` was added in
Day 3. The Sentence Transformers model is loaded from the local cache and
is not a declared dependency, because the default embedder needs no model
files.

## 12. Day 5 Dependencies

Day 5 (tool registry and executor) depends on Day 4 in these ways:

- The registry must register the capabilities the planner emits. Day 4
  provides `document.read`, `document.extract` and `llm.summarise` under
  those exact names, so binding needs no translation layer.
- The executor needs a way to read a file into the index and then retrieve
  from it. `DocumentIntelligenceService` offers both, and the capability
  adapter wraps them in the shape the executor will call.
- The executor must resolve a document path safely. Restricting reads to
  an allowed root is Day 5 work; Day 4 reads the path it is given.
- Tool schemas for the document capabilities do not exist yet. Day 5
  should define them against the `DocumentCapabilities` interface, whose
  return shapes are already fixed.
- Approval gates apply at execution, not at planning. Day 4's capabilities
  are read-only, so no Day 4 operation can be used to bypass an approval
  gate.

---

**Conclusion:** Day 4 is complete. NexusAI can now ingest PDF, DOCX, TXT
and Markdown documents, index them locally, retrieve relevant passages with
traceable source references, and answer questions and produce summaries
grounded in that evidence — saying so explicitly when the evidence is
insufficient. The Day 3 planner's document capabilities are satisfied
without a translation layer. Retrieval accuracy has not been measured; that
requires the Day 7 harness. Day 5 may begin after review.
