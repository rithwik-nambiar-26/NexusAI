"""Local vector store for the RAG subsystem.

A small, dependency-light store built on numpy. It holds chunk embeddings
in memory, persists them to disk as a compressed archive, and retrieves by
cosine similarity.

The store is deliberately local and inspectable: it is a directory of
files under ``artifacts/vectors/`` that a researcher can open and read.
That suits the project's local-first constraint and keeps the dependency
surface small; a third-party vector database can be substituted later
behind the same interface.

Metadata filters are applied before scoring, so a filtered retrieval never
returns a chunk that merely scored highly.
"""

from __future__ import annotations

import json
import pickle
import shutil
from pathlib import Path

import numpy as np

from nexusai.rag.schemas import Chunk, RetrievedChunk


class VectorStore:
    """An in-memory vector index with on-disk persistence.

    Attributes:
        path: Directory the store is persisted to.
        dimension: Dimensionality of the stored vectors.
    """

    def __init__(self, path: Path | str, dimension: int) -> None:
        self.path = Path(path)
        self.dimension = dimension
        self._chunks: dict[str, Chunk] = {}
        self._document_names: dict[str, str] = {}
        self._vectors: dict[str, np.ndarray] = {}
        self._matrix: np.ndarray | None = None
        self._ids: list[str] = []

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------
    def add(
        self,
        chunk: Chunk,
        vector: np.ndarray,
        document_name: str = "",
    ) -> None:
        """Add a chunk and its embedding to the store.

        Re-adding a chunk id replaces the previous entry, so re-ingesting
        a document is idempotent.
        """
        if vector.shape[0] != self.dimension:
            raise ValueError(
                f"Vector has dimension {vector.shape[0]}, expected {self.dimension}"
            )

        chunk_id = chunk.chunk_id
        if chunk_id not in self._chunks:
            self._ids.append(chunk_id)

        self._chunks[chunk_id] = chunk
        self._document_names[chunk_id] = document_name
        self._vectors[chunk_id] = np.asarray(vector, dtype=np.float32)
        self._matrix = None

    def add_many(
        self,
        chunks: list[Chunk],
        vectors: np.ndarray,
        document_names: dict[str, str] | None = None,
    ) -> None:
        """Add many chunks and their embeddings."""
        if len(chunks) != len(vectors):
            raise ValueError(
                f"Got {len(chunks)} chunks but {len(vectors)} vectors"
            )
        names = document_names or {}
        for chunk, vector in zip(chunks, vectors, strict=True):
            self.add(chunk, vector, names.get(chunk.document_id, ""))

    def remove_document(self, document_id: str) -> int:
        """Remove every chunk belonging to a document.

        Returns:
            The number of chunks removed.
        """
        to_remove = [
            chunk_id
            for chunk_id, chunk in self._chunks.items()
            if chunk.document_id == document_id
        ]
        for chunk_id in to_remove:
            self._chunks.pop(chunk_id, None)
            self._document_names.pop(chunk_id, None)
            self._vectors.pop(chunk_id, None)
        if to_remove:
            self._ids = [cid for cid in self._ids if cid not in set(to_remove)]
            self._matrix = None
        return len(to_remove)

    def clear(self) -> None:
        """Remove every chunk from the store."""
        self._chunks.clear()
        self._document_names.clear()
        self._vectors.clear()
        self._ids.clear()
        self._matrix = None

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------
    def __len__(self) -> int:
        return len(self._chunks)

    def __contains__(self, chunk_id: str) -> bool:
        return chunk_id in self._chunks

    def has_document(self, document_id: str) -> bool:
        """Return True when the store holds chunks for a document."""
        return any(
            chunk.document_id == document_id for chunk in self._chunks.values()
        )

    def get_chunk(self, chunk_id: str) -> Chunk | None:
        """Return a chunk by id."""
        return self._chunks.get(chunk_id)

    def get_document_name(self, chunk_id: str) -> str:
        """Return the display name of the document owning a chunk."""
        return self._document_names.get(chunk_id, "")

    def all_chunks(self) -> list[Chunk]:
        """Return every chunk, in insertion order."""
        return [self._chunks[chunk_id] for chunk_id in self._ids if chunk_id in self._chunks]

    def chunks_for_document(self, document_id: str) -> list[Chunk]:
        """Return every chunk belonging to a document, in chunk order."""
        return [c for c in self.all_chunks() if c.document_id == document_id]

    def document_ids(self) -> set[str]:
        """Return the set of document ids held by the store."""
        return {chunk.document_id for chunk in self._chunks.values()}

    def _rebuild_matrix(self) -> np.ndarray:
        if self._matrix is None:
            if self._ids:
                self._matrix = np.vstack([self._vectors[cid] for cid in self._ids])
            else:
                self._matrix = np.zeros((0, self.dimension), dtype=np.float32)
        return self._matrix

    def search(
        self,
        query_vector: np.ndarray,
        top_k: int = 5,
        min_score: float = 0.0,
        document_ids: set[str] | None = None,
    ) -> list[RetrievedChunk]:
        """Return the chunks most similar to *query_vector*.

        Args:
            query_vector: The query embedding. Must match the store's
                dimensionality.
            top_k: Maximum number of results to return.
            min_score: Minimum cosine similarity a result must reach.
            document_ids: When given, only chunks from these documents are
                considered. The filter is applied before scoring, so a
                filtered search never returns an out-of-scope chunk.

        Returns:
            Results ordered by descending score, each carrying its source
            reference.
        """
        query = np.asarray(query_vector, dtype=np.float32)
        if query.shape[0] != self.dimension:
            raise ValueError(
                f"Query has dimension {query.shape[0]}, expected {self.dimension}"
            )

        if not self._chunks:
            return []

        candidates = [
            chunk_id
            for chunk_id in self._ids
            if document_ids is None or self._chunks[chunk_id].document_id in document_ids
        ]
        if not candidates:
            return []

        matrix = np.vstack([self._vectors[cid] for cid in candidates])
        scores = matrix @ query

        ranked = sorted(
            zip(candidates, scores.tolist(), strict=True),
            key=lambda item: (-item[1], item[0]),
        )

        results: list[RetrievedChunk] = []
        for rank, (chunk_id, score) in enumerate(ranked, start=1):
            if score < min_score:
                break
            chunk = self._chunks[chunk_id]
            document_name = self._document_names.get(chunk_id, "")
            results.append(
                RetrievedChunk(
                    chunk=chunk,
                    score=float(score),
                    document_name=document_name,
                    source_reference=chunk.source_reference(document_name),
                    rank=rank,
                )
            )
            if len(results) >= top_k:
                break

        return results

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def save(self) -> None:
        """Persist the store to disk."""
        self.path.mkdir(parents=True, exist_ok=True)

        payload = {
            "dimension": self.dimension,
            "ids": self._ids,
            "chunks": self._chunks,
            "document_names": self._document_names,
            "vectors": self._vectors,
        }
        with open(self.path / "store.pkl", "wb") as handle:
            pickle.dump(payload, handle, protocol=pickle.HIGHEST_PROTOCOL)

        manifest = {
            "dimension": self.dimension,
            "chunk_count": len(self._chunks),
            "document_ids": sorted(self.document_ids()),
        }
        (self.path / "manifest.json").write_text(json.dumps(manifest, indent=2))

    def load(self) -> bool:
        """Load the store from disk.

        Returns:
            True when a store was loaded, False when none was present.
        """
        store_file = self.path / "store.pkl"
        if not store_file.exists():
            return False

        try:
            with open(store_file, "rb") as handle:
                payload = pickle.load(handle)
        except (EOFError, OSError, pickle.UnpicklingError):
            return False

        self.dimension = int(payload.get("dimension", self.dimension))
        self._ids = list(payload.get("ids", []))
        self._chunks = dict(payload.get("chunks", {}))
        self._document_names = dict(payload.get("document_names", {}))
        self._vectors = dict(payload.get("vectors", {}))
        self._matrix = None
        return True

    def delete(self) -> None:
        """Remove the store's directory from disk."""
        if self.path.exists():
            shutil.rmtree(self.path)
