"""Tests for the local vector store."""

from __future__ import annotations

import numpy as np
import pytest

from nexusai.rag.schemas import Chunk
from nexusai.rag.store import VectorStore


def _chunk(chunk_id: str, text: str, document_id: str = "doc_1", index: int = 0) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        document_id=document_id,
        text=text,
        chunk_index=index,
        page_number=1,
        heading="Heading",
    )


def _vector(value: float, dimension: int = 4) -> np.ndarray:
    """Return a unit vector whose similarity with the query scales with value."""
    vector = np.zeros(dimension, dtype=np.float32)
    vector[0] = value
    vector[1] = 1.0
    return vector / np.linalg.norm(vector)


def _low_similarity_vector(dimension: int = 4) -> np.ndarray:
    """Return a unit vector nearly orthogonal to the query vector."""
    vector = np.zeros(dimension, dtype=np.float32)
    vector[1] = 1.0
    vector[2] = 1.0
    return vector / np.linalg.norm(vector)


def test_store_add_and_len():
    """Test that adding chunks increases the store size."""
    store = VectorStore("/tmp/unused", dimension=4)
    store.add(_chunk("c1", "first"), _vector(1.0))
    assert len(store) == 1
    assert "c1" in store


def test_store_rejects_wrong_dimension():
    """Test that a mismatched vector is rejected."""
    store = VectorStore("/tmp/unused", dimension=4)
    with pytest.raises(ValueError):
        store.add(_chunk("c1", "first"), np.zeros(3, dtype=np.float32))


def test_store_add_is_idempotent():
    """Test that re-adding the same chunk id replaces it."""
    store = VectorStore("/tmp/unused", dimension=4)
    store.add(_chunk("c1", "first"), _vector(1.0))
    store.add(_chunk("c1", "second"), _vector(0.5))
    assert len(store) == 1
    assert store.get_chunk("c1").text == "second"


def test_store_search_orders_by_score():
    """Test that results are ordered by descending similarity."""
    store = VectorStore("/tmp/unused", dimension=4)
    store.add(_chunk("c1", "low"), _vector(0.1))
    store.add(_chunk("c2", "high"), _vector(1.0))

    results = store.search(_vector(1.0), top_k=2)
    assert [r.chunk.chunk_id for r in results] == ["c2", "c1"]
    assert results[0].score > results[1].score


def test_store_search_respects_top_k():
    """Test that top_k limits the number of results."""
    store = VectorStore("/tmp/unused", dimension=4)
    for index in range(5):
        store.add(_chunk(f"c{index}", "text"), _vector(1.0 - index * 0.1))

    assert len(store.search(_vector(1.0), top_k=2)) == 2


def test_store_search_applies_min_score():
    """Test that low-scoring results are excluded."""
    store = VectorStore("/tmp/unused", dimension=4)
    store.add(_chunk("c1", "high"), _vector(1.0))
    store.add(_chunk("c2", "low"), _low_similarity_vector())

    results = store.search(_vector(1.0), top_k=5, min_score=0.5)
    assert [r.chunk.chunk_id for r in results] == ["c1"]


def test_store_search_filters_by_document():
    """Test that a document filter excludes other documents' chunks."""
    store = VectorStore("/tmp/unused", dimension=4)
    store.add(_chunk("c1", "in scope", document_id="doc_1"), _vector(1.0))
    store.add(_chunk("c2", "out of scope", document_id="doc_2"), _vector(1.0))

    results = store.search(_vector(1.0), top_k=5, document_ids={"doc_1"})
    assert [r.chunk.chunk_id for r in results] == ["c1"]


def test_store_search_empty_store():
    """Test that searching an empty store returns nothing."""
    store = VectorStore("/tmp/unused", dimension=4)
    assert store.search(_vector(1.0)) == []


def test_store_search_rejects_wrong_dimension():
    """Test that a mismatched query is rejected."""
    store = VectorStore("/tmp/unused", dimension=4)
    with pytest.raises(ValueError):
        store.search(np.zeros(3, dtype=np.float32))


def test_store_remove_document():
    """Test that removing a document removes only its chunks."""
    store = VectorStore("/tmp/unused", dimension=4)
    store.add(_chunk("c1", "a", document_id="doc_1"), _vector(1.0))
    store.add(_chunk("c2", "b", document_id="doc_1"), _vector(1.0))
    store.add(_chunk("c3", "c", document_id="doc_2"), _vector(1.0))

    assert store.remove_document("doc_1") == 2
    assert len(store) == 1
    assert store.document_ids() == {"doc_2"}


def test_store_has_document():
    """Test the document membership check."""
    store = VectorStore("/tmp/unused", dimension=4)
    store.add(_chunk("c1", "a", document_id="doc_1"), _vector(1.0))
    assert store.has_document("doc_1") is True
    assert store.has_document("doc_9") is False


def test_store_save_and_load(tmp_path):
    """Test that a store survives a save and load cycle."""
    store = VectorStore(tmp_path / "vectors", dimension=4)
    store.add(_chunk("c1", "first"), _vector(1.0))
    store.add(_chunk("c2", "second", document_id="doc_2", index=1), _vector(0.5))
    store.save()

    assert (tmp_path / "vectors" / "store.pkl").exists()
    assert (tmp_path / "vectors" / "manifest.json").exists()

    loaded = VectorStore(tmp_path / "vectors", dimension=4)
    assert loaded.load() is True
    assert len(loaded) == 2
    assert loaded.get_chunk("c1").text == "first"
    assert loaded.document_ids() == {"doc_1", "doc_2"}

    # The loaded store is still usable for retrieval.
    results = loaded.search(_vector(1.0), top_k=2)
    assert results


def test_store_load_missing_returns_false(tmp_path):
    """Test that loading a missing store reports failure."""
    store = VectorStore(tmp_path / "nothing", dimension=4)
    assert store.load() is False


def test_store_load_corrupt_returns_false(tmp_path):
    """Test that a corrupt store file is reported rather than raising."""
    path = tmp_path / "vectors"
    path.mkdir(parents=True)
    (path / "store.pkl").write_bytes(b"not a pickle")

    store = VectorStore(path, dimension=4)
    assert store.load() is False


def test_store_clear():
    """Test that clearing empties the store."""
    store = VectorStore("/tmp/unused", dimension=4)
    store.add(_chunk("c1", "a"), _vector(1.0))
    store.clear()
    assert len(store) == 0


def test_store_all_chunks_preserves_order():
    """Test that all_chunks returns chunks in insertion order."""
    store = VectorStore("/tmp/unused", dimension=4)
    for index in range(3):
        store.add(_chunk(f"c{index}", "text", index=index), _vector(1.0))
    assert [c.chunk_id for c in store.all_chunks()] == ["c0", "c1", "c2"]


def test_store_chunks_for_document():
    """Test filtering chunks by document."""
    store = VectorStore("/tmp/unused", dimension=4)
    store.add(_chunk("c1", "a", document_id="doc_1"), _vector(1.0))
    store.add(_chunk("c2", "b", document_id="doc_2"), _vector(1.0))
    assert len(store.chunks_for_document("doc_1")) == 1


def test_store_result_carries_source_reference():
    """Test that results carry a human-readable source reference."""
    store = VectorStore("/tmp/unused", dimension=4)
    store.add(_chunk("c1", "a"), _vector(1.0), document_name="manual.md")
    result = store.search(_vector(1.0), top_k=1)[0]
    assert result.document_name == "manual.md"
    assert "manual.md" in result.source_reference
    assert "c1" in result.source_reference
