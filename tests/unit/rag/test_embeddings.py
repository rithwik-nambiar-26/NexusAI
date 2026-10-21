"""Tests for local embedding generation."""

from __future__ import annotations

import numpy as np
import pytest

from nexusai.rag.embeddings import (
    EmbeddingError,
    HashingEmbedder,
    SentenceTransformerEmbedder,
    get_embedder,
    tokenize,
)


def test_tokenize_splits_words():
    """Test that tokenisation lowercases and splits on non-word characters."""
    assert tokenize("Hello, World! 42") == ["hello", "world", "42"]


def test_hashing_embedder_is_deterministic():
    """Test that the same input always produces the same vector."""
    embedder = HashingEmbedder()
    first = embedder.embed(["warranty period"])
    second = embedder.embed(["warranty period"])
    assert np.allclose(first, second)


def test_hashing_embedder_shape():
    """Test the shape of the produced matrix."""
    embedder = HashingEmbedder()
    vectors = embedder.embed(["one", "two", "three"])
    assert vectors.shape == (3, embedder.dimension)
    assert vectors.dtype == np.float32


def test_hashing_embedder_normalises_rows():
    """Test that vectors are L2-normalised so a dot product is cosine."""
    embedder = HashingEmbedder()
    vectors = embedder.embed(["warranty period for the widget"])
    norms = np.linalg.norm(vectors, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-5)


def test_hashing_embedder_empty_input():
    """Test that an empty batch produces an empty matrix."""
    embedder = HashingEmbedder()
    vectors = embedder.embed([])
    assert vectors.shape == (0, embedder.dimension)


def test_hashing_embedder_similar_text_scores_higher():
    """Test that related text scores higher than unrelated text."""
    embedder = HashingEmbedder()
    query = embedder.embed(["warranty coverage for the device"])[0]
    related = embedder.embed(["the device warranty covers defects"])[0]
    unrelated = embedder.embed(["quarterly revenue by region"])[0]

    assert float(query @ related) > float(query @ unrelated)


def test_hashing_embedder_handles_empty_text():
    """Test that empty text does not produce a NaN vector."""
    embedder = HashingEmbedder()
    vectors = embedder.embed(["", "real content"])
    assert not np.isnan(vectors).any()


def test_get_embedder_by_name():
    """Test that embedders are resolved by name."""
    assert isinstance(get_embedder("hashing"), HashingEmbedder)
    assert isinstance(get_embedder("sentence_transformers"), SentenceTransformerEmbedder)


def test_get_embedder_unknown_name():
    """Test that an unknown embedder name is rejected."""
    with pytest.raises(EmbeddingError):
        get_embedder("does_not_exist")


def test_sentence_transformer_embedder_reports_dimension():
    """Test that the model dimension is reported without failing hard.

    The embedder is optional: the hashing embedder is the default and
    sentence-transformers need not be installed. This test therefore only
    asserts the dimension when the library and model are both available.
    """
    embedder = SentenceTransformerEmbedder()
    try:
        dimension = embedder.dimension
    except EmbeddingError:
        pytest.skip("sentence-transformers is not installed in this environment")
    assert isinstance(dimension, int)
    assert dimension > 0


def test_sentence_transformer_embedder_missing_model_raises():
    """Test that a missing model produces a clear error, not a hang."""
    embedder = SentenceTransformerEmbedder(model_name="nonexistent/model-xyz")
    with pytest.raises(EmbeddingError):
        embedder.embed(["hello"])


def test_sentence_transformer_empty_batch():
    """Test that an empty batch is handled."""
    embedder = SentenceTransformerEmbedder()
    try:
        vectors = embedder.embed([])
    except EmbeddingError:
        pytest.skip("sentence-transformers model not available locally")
    assert vectors.shape[0] == 0
