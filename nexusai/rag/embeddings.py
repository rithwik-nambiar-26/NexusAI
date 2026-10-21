"""Local embedding generation for the RAG subsystem.

Two embedders are provided:

* :class:`SentenceTransformerEmbedder` uses a local Sentence Transformers
  model. The model is loaded from the local cache; no inference service is
  contacted. If the model is not present the embedder raises a clear
  error rather than silently downloading anything.
* :class:`HashingEmbedder` is a deterministic, dependency-free embedder
  built on the hashing trick. It needs no model files and no network, so
  the whole extraction, chunking, indexing and retrieval pipeline stays
  testable when no model is available.

Both embedders return L2-normalised float32 matrices so that a dot
product is a cosine similarity.
"""

from __future__ import annotations

import hashlib
import re
from itertools import pairwise
from typing import Protocol, runtime_checkable

import numpy as np

#: Default model name for the sentence-transformers embedder.
DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

#: Dimension of the hashing embedder.
HASHING_DIMENSION = 384

#: The hashing embedder is the default so that the pipeline works with no
#: model files present and no network access.
DEFAULT_EMBEDDER = "hashing"

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Return the lowercase word tokens of *text*."""
    return _TOKEN_RE.findall(text.lower())


class EmbeddingError(Exception):
    """Raised when embeddings cannot be produced."""


@runtime_checkable
class Embedder(Protocol):
    """Interface for an embedder.

    Implementations must be deterministic for the same input, and must
    return L2-normalised vectors so that a dot product is a cosine
    similarity.
    """

    @property
    def dimension(self) -> int:
        """The dimensionality of the produced vectors."""
        ...

    def embed(self, texts: list[str]) -> np.ndarray:
        """Embed a batch of texts.

        Args:
            texts: The texts to embed.

        Returns:
            A float32 array of shape ``(len(texts), dimension)``.
        """
        ...


def _normalize(matrix: np.ndarray) -> np.ndarray:
    """L2-normalise each row of *matrix*, leaving zero rows untouched."""
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    return (matrix / norms).astype(np.float32)


class HashingEmbedder:
    """Deterministic hashing embedder with no external dependencies.

    Text is tokenised into words and word bigrams. Each feature is hashed
    into a fixed number of buckets and weighted by the term frequency.
    Collisions are possible but the vectors are stable across runs and
    machines, which is what the test suite relies on.
    """

    def __init__(self, dimension: int = HASHING_DIMENSION, use_bigrams: bool = True) -> None:
        self._dimension = dimension
        self._use_bigrams = use_bigrams

    @property
    def dimension(self) -> int:
        """The dimensionality of the produced vectors."""
        return self._dimension

    def _features(self, text: str) -> list[str]:
        tokens = tokenize(text)
        features = list(tokens)
        if self._use_bigrams:
            features.extend(f"{a}_{b}" for a, b in pairwise(tokens))
        return features

    def _bucket(self, feature: str) -> int:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        return int.from_bytes(digest, "big") % self._dimension

    def _sign(self, feature: str) -> float:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        return 1.0 if digest[0] % 2 == 0 else -1.0

    def embed(self, texts: list[str]) -> np.ndarray:
        """Embed a batch of texts deterministically."""
        if not texts:
            return np.zeros((0, self._dimension), dtype=np.float32)

        matrix = np.zeros((len(texts), self._dimension), dtype=np.float32)
        for row, text in enumerate(texts):
            counts: dict[str, int] = {}
            for feature in self._features(text):
                counts[feature] = counts.get(feature, 0) + 1
            for feature, count in counts.items():
                # Sub-linear term frequency, matching the TF-IDF convention
                # used elsewhere in the project.
                weight = (1.0 + np.log(count)) * self._sign(feature)
                matrix[row, self._bucket(feature)] += weight

        return _normalize(matrix)


class SentenceTransformerEmbedder:
    """Embedder backed by a local Sentence Transformers model.

    The model is loaded from the local cache only. If it is not available
    an :class:`EmbeddingError` is raised; the embedder never triggers a
    download on its own.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        device: str | None = None,
        allow_download: bool = False,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.allow_download = allow_download
        self._model = None
        self._dimension = 0

    def _load(self):
        if self._model is not None:
            return self._model

        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise EmbeddingError(
                "sentence-transformers is not installed. "
                "Install it with: pip install sentence-transformers"
            ) from exc

        try:
            model = SentenceTransformer(self.model_name, device=self.device)
        except Exception as exc:
            raise EmbeddingError(
                f"Could not load local model '{self.model_name}': {exc}. "
                "Download the model first, or use the hashing embedder instead."
            ) from exc

        self._model = model
        # `get_sentence_embedding_dimension` was renamed in newer
        # sentence-transformers releases; support both spellings.
        if hasattr(model, "get_embedding_dimension"):
            self._dimension = int(model.get_embedding_dimension())
        else:  # pragma: no cover - older sentence-transformers
            self._dimension = int(model.get_sentence_embedding_dimension())
        return model

    @property
    def dimension(self) -> int:
        """The dimensionality of the produced vectors."""
        if self._dimension == 0:
            self._load()
        return self._dimension

    def embed(self, texts: list[str]) -> np.ndarray:
        """Embed a batch of texts with the local model."""
        if not texts:
            return np.zeros((0, self.dimension), dtype=np.float32)

        model = self._load()
        try:
            vectors = model.encode(
                texts,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        except Exception as exc:
            raise EmbeddingError(f"Embedding failed: {exc}") from exc

        return np.asarray(vectors, dtype=np.float32)


def get_embedder(name: str = DEFAULT_EMBEDDER) -> Embedder:
    """Return an embedder by name.

    Args:
        name: ``"hashing"`` for the dependency-free deterministic embedder,
            or ``"sentence_transformers"`` for the local model.

    Raises:
        EmbeddingError: The name is not recognised.
    """
    if name == "hashing":
        return HashingEmbedder()
    if name in ("sentence_transformers", "st", "minilm"):
        return SentenceTransformerEmbedder()
    raise EmbeddingError(f"Unknown embedder: {name}")
