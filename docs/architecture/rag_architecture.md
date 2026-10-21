# RAG Architecture

**Project:** NexusAI  
**Document status:** Draft v0.1 — Phase 1, Day 4  
**Date:** 2026-10-21  
**Research objective:** O3 — RAG over user-provided documents

## 1. Purpose

This document specifies the document intelligence module introduced in Day 4:
how documents are ingested and validated, how their text is extracted,
normalised and chunked, how chunks are embedded and indexed, how relevant
passages are retrieved, and how questions and summaries are answered from
that evidence with traceable source references.

Three properties shape the design:

- **Evidence, not assertion.** An answer is assembled from retrieved source
  text, and every span it uses carries a source reference. When the
  evidence does not support an answer, the service says so explicitly.
- **Local and open.** Everything runs on the local machine with open-source
  libraries. No paid API, cloud inference or proprietary service is
  involved.
- **Documents are data.** Text found inside a document is quoted, never
  obeyed. Nothing in a document is executed.

## 2. Component map

```
   file on disk                     text in band
        |                                |
        v                                v
   +------------------------------------------------+
   |  Ingestion and validation                      |
   |  (nexusai/rag/extractors.py)                   |
   |  PDF | DOCX | TXT | Markdown                   |
   +------------------------+-----------------------+
                            |
                            v
   +------------------------------------------------+
   |  Normalisation and chunking                    |
   |  (nexusai/rag/chunking.py)                     |
   |  stable ids, source offsets, headings          |
   +------------------------+-----------------------+
                            |
                            v
   +------------------------------------------------+
   |  Embedding (nexusai/rag/embeddings.py)         |
   |  hashing (default) | sentence-transformers      |
   +------------------------+-----------------------+
                            |
                            v
   +------------------------------------------------+
   |  Vector index (nexusai/rag/store.py)           |
   |  numpy, cosine similarity, metadata filters   |
   +------------------------+-----------------------+
                            |
                            v
   +------------------------------------------------+
   |  Retrieval and answer construction             |
   |  (nexusai/rag/service.py)                      |
   |  retrieve | answer | summarise                 |
   +------------------------+-----------------------+
                            |
                            v
   +------------------------------------------------+
   |  Capability adapter                            |
   |  (nexusai/rag/capabilities.py)                 |
   |  document.read | document.extract | llm.summarise
   +------------------------------------------------+
```

## 3. Module boundaries

| Module | Responsibility |
|--------|----------------|
| `nexusai/rag/schemas.py` | Pydantic contracts: documents, sections, chunks, evidence, answers, summaries |
| `nexusai/rag/extractors.py` | File to text, with page numbers and headings preserved |
| `nexusai/rag/chunking.py` | Normalisation, paragraph packing, stable identifiers |
| `nexusai/rag/embeddings.py` | The `Embedder` protocol, a hashing embedder and a Sentence Transformers embedder |
| `nexusai/rag/store.py` | The vector index: add, search, filter, persist |
| `nexusai/rag/service.py` | Ingestion, retrieval, grounded answers, grounded summaries |
| `nexusai/rag/capabilities.py` | Adapter exposing the operations under the planner's capability names |
| `nexusai/app/api/routes/rag.py` | HTTP surface |

The service layer has no FastAPI dependency, so it can be driven from the
CLI, the Streamlit UI, the experiment harness or the API.

## 4. Supported formats

| Format | Extension | Library | Pages | Headings |
|--------|-----------|---------|-------|----------|
| PDF | `.pdf` | PyMuPDF | Yes | First short line of a page |
| DOCX | `.docx` | python-docx | No | Heading paragraphs |
| Text | `.txt`, `.text` | standard library | No | No |
| Markdown | `.md`, `.markdown` | standard library | No | ATX headings |

Text is decoded as UTF-8, then UTF-8 with BOM, then Latin-1, so a file
with an unexpected encoding still yields text rather than an error.

An unsupported extension is reported as `unsupported_format`; a file that
exists but cannot be parsed is reported as `corrupted`; a file with no
extractable text is reported as `empty`. Ingestion never raises for bad
input — it returns a status the caller can act on.

## 5. Chunking design

Normalisation (`normalize_text`) applies Unicode NFC normalisation, removes
soft hyphens, normalises line endings, collapses trailing spaces and
reduces runs of blank lines to one. It deliberately does not change words,
punctuation or case, because the normalised text is what citations are
checked against.

Chunking packs paragraphs into windows of at most `chunk_size` characters
(800 by default) with `chunk_overlap` characters of overlap (100). A
paragraph longer than the target is split on sentence boundaries, and
failing that on word boundaries, so no content is silently dropped.

Every chunk carries:

| Field | Purpose |
|-------|---------|
| `chunk_id` | Stable, content-addressed identifier |
| `document_id` | Owning document |
| `text` | The chunk text, verbatim |
| `chunk_index` | Position within the document |
| `page_number` | 1-based page, where the format has pages |
| `heading` | Nearest heading above the chunk |
| `start_offset`, `end_offset` | Location within the document's extracted text |
| `token_estimate` | Approximate token count |

**Stable identifiers.** A document id is a hash of the document name and
its normalised text. A chunk id is a hash of the document id, the chunk
index and the chunk text. The same file ingested twice therefore yields
the same identifiers, which is what makes duplicate detection possible.

**Offset preservation.** Section and chunk offsets locate the text in the
document's extracted text, so the original source can be recovered
verbatim. This is what lets a later verification step check a quoted
sentence against the document rather than against a paraphrase.

## 6. Embedding and the vector index

### Embedders

| Embedder | Model | Network | Notes |
|-----------|-------|---------|-------|
| `HashingEmbedder` (default) | none | none | Deterministic hashing trick, 384 dimensions, dependency-free |
| `SentenceTransformerEmbedder` | `all-MiniLM-L6-v2` | none (local cache) | 384 dimensions, loads from the local model cache |

The hashing embedder is the default so that the whole pipeline —
extraction, chunking, indexing, retrieval — works with no model files
present and no network access. This is what keeps the test suite
deterministic and fast.

The Sentence Transformers embedder loads a model from the local cache. If
the model is not present it raises `EmbeddingError` with a clear message;
it never triggers a download on its own. Both embedders return
L2-normalised float32 matrices, so a dot product is a cosine similarity.

### Vector index

`VectorStore` is a small numpy-backed index:

- One entry per chunk, holding the chunk, its vector and its document name
- Search computes cosine similarity against a query vector
- A document filter is applied **before** scoring, so a filtered search can
  never return an out-of-scope chunk
- Results are ordered by descending score, with the chunk id as a
  tie-breaker, so ordering is deterministic
- The store persists to `artifacts/vectors/` as a pickle plus a readable
  `manifest.json`

**Why not ChromaDB?** ChromaDB was installed and evaluated. It was
rejected because it pulls in a large dependency tree (OpenTelemetry,
Kubernetes, OAuth libraries) for functionality this project does not need
yet, it ships an `anonymized_telemetry` module that conflicts with the
project's local-first, nothing-leaves-the-machine requirement, and its
installation changed unrelated packages in the environment. A numpy index
is roughly a hundred lines, is fully deterministic, is inspectable by a
researcher, and keeps the dependency surface small. The `VectorStore`
interface is narrow enough that a different backend can be substituted
later. This is recorded as AD-17.

## 7. Retrieval and the citation mechanism

`retrieve(query, top_k, min_score, document_ids)` returns
`RetrievedChunk` objects, each carrying:

| Field | Purpose |
|-------|---------|
| `chunk` | The chunk itself, with its source metadata |
| `score` | Cosine similarity against the query |
| `document_name` | Display name of the owning document |
| `source_reference` | Human-readable citation |
| `rank` | 1-based position |

A source reference is built as `document name | p.N | §heading | chunk_id`,
for example:

```
product_manual.md | p.2 | 2.1 Warranty exclusions | chunk_fba6d6994cbee60a
```

The page number is included only when the format has pages. The chunk id
is always included, so a citation resolves to exactly one indexed span.

**Similarity is not truth.** A score says a passage looks relevant to the
query. It says nothing about whether the passage is factually correct, and
the API description says so. The `evidence_accuracy` metric in
`evaluation_metrics.md` is what measures whether a cited passage actually
supports a claim, and it is not yet computed.

## 8. Answer construction

Retrieval and answer construction are separate steps. Retrieval produces
evidence; the answer is assembled from that evidence.

The answer builder selects, for each retrieved passage, the sentence that
best addresses the question, and then applies two filters:

1. **A sentence must share a term with the question.** A passage sharing
   nothing contributes nothing, so unrelated passages are never included
   merely to fill a result count.
2. **Matching is weighted by inverse document frequency.** A term that
   occurs in many chunks ("period") counts for less than a distinctive one
   ("warranty"). The weights are computed over the indexed corpus, so they
   describe this corpus rather than a universal constant.

Terms are lightly stemmed and matched by prefix, so "exclude", "excluded"
and "exclusion" are recognised as the same word. A chunk's heading
contributes to the match as well: a passage under "Warranty exclusions" is
recognised as answering a question about exclusions even when the sentence
itself does not repeat the word.

Only sentences reaching a fraction of the best weighted score are kept, so
a single strong match is not diluted by weak ones. The passage-level
retrieval score is filtered the same way.

The resulting `Answer` carries the `answer_text`, the `evidence` spans
used, their `citations`, and a `confidence` equal to the highest evidence
score.

### Insufficient evidence

The service distinguishes three outcomes:

| Status | When | `answer_text` |
|--------|------|---------------|
| `answered` | Evidence supports the question | The grounded answer |
| `insufficient_evidence` | Passages were retrieved but none addresses the question | Empty |
| `no_documents` | Nothing is indexed | Empty |

When the outcome is `insufficient_evidence`, `insufficient_reason`
explains why, and `evidence` is empty. The service never falls back to
generating a plausible-sounding answer.

## 9. Summarisation

`summary` is extractive: it selects representative sentences from the
source text and cites them. It does not generate new prose, so every
sentence in the summary can be checked against the source.

Summarising a named document uses that document's chunks in source order.
Summarising without a document and without a question uses the first
chunks of the index, also in source order, so a summary reads in the
order the document was written rather than by score.

## 10. Safety

| Concern | Handling |
|---------|----------|
| Document content treated as instructions | Content is quoted as data. A pattern check flags instruction-like passages so a reviewer can see them; flagged content is still indexed and still quoted. Nothing in a document is obeyed. |
| Code execution | There is no `eval`, `exec`, `subprocess` or shell access anywhere in the module. |
| Fabricated citations | Every citation is built from the chunk's own stored metadata. A chunk that was not retrieved cannot be cited. |
| Fabricated page numbers | `page_number` is `None` unless the format supplies real page boundaries. |
| Fabricated evidence | The evidence span text is copied verbatim from the indexed chunk; a test asserts the quoted text appears in the source document. |
| Retrieval returning junk to fill a count | A passage must share a term with the question and reach the relative score floor. |
| Unsound file handling | Unsupported formats, corrupt files and empty files are reported as statuses, not crashes. |
| Path traversal | The API takes a path from the caller; the service reads it as given. Restricting reads to an allowed root is Day 5 executor work, when the tool registry defines what may be read. |

## 11. Planner capability compatibility

The Day 3 planner names the tools a task needs in `required_capabilities`.
`nexusai/rag/capabilities.py` exposes the operations under exactly those
names, so the Day 5 registry can bind a planner task without a
translation layer:

| Capability | Operation | Returns |
|------------|-----------|---------|
| `document.read` | Read a document and return its extracted text | Document text, sections, page count, format |
| `document.extract` | Retrieve the passages relevant to a query | Passages with scores and source references |
| `llm.summarise` | Produce a grounded summary | Summary text, citations, evidence |

A planner task for document summarisation requires
`document.read`, `document.extract` and `llm.summarise`; all three are
served by this module. `verify.content` is not served here — it belongs
to the Day 6 verifier, which must stay separate from the planner.

The adapter is deliberately thin and read-only. It exposes no write, send
or delete operation, so binding a planner task to it cannot authorise
anything.

## 12. API surface

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v1/documents/ingest` | Ingest a document from disk |
| POST | `/api/v1/documents/ingest-text` | Ingest text supplied in the request |
| GET | `/api/v1/documents` | List the indexed documents |
| POST | `/api/v1/documents/retrieve` | Retrieve relevant passages |
| POST | `/api/v1/documents/answer` | Answer a question from the indexed documents |
| POST | `/api/v1/documents/summarise` | Summarise a document or the corpus |
| GET | `/api/v1/documents/capabilities` | List the planner capabilities satisfied |

The document service is **application-scoped**: each application instance
owns its own vector index, so a test application never reads or writes the
developer's working index. The store directory comes from the
`vector_store_dir` setting, resolved against the repository root.

## 13. What is not implemented

- An LLM generative answer or summary. Both are extractive. A generative
  backend can be added behind the same service interface.
- Reranking, query expansion, hybrid lexical plus dense retrieval, or
  reciprocal-rank fusion.
- A table-aware or layout-aware PDF parser. Text is extracted in page
  order; tables are read as text.
- OCR for scanned PDFs.
- The `evidence_accuracy` metric. The definition exists in
  `evaluation_metrics.md`; the measurement needs the Day 7 harness.
- A per-document corpus restriction on `ingest_text` beyond the name.
- Multi-document conversational retrieval.

---

**Traceability:** This component implements O3 and contributes to C5 in
`research_gap.md` (RAG over a user-provided local corpus with cited
evidence). It supplies the evidence that the planner's document tasks
require, and the evidence that the Day 6 verifier will check, which is
the input to the `evidence_accuracy` metric in `evaluation_metrics.md`.
