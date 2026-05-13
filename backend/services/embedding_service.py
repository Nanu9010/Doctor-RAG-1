"""
services/embedding_service.py

Singleton embedding model — loaded once at startup to avoid
reloading the 80MB+ model on each request.

Thread-safe: sentence-transformers encode() releases the GIL
so this is safe for concurrent Flask workers.
"""
import os
import logging
import threading
from typing import TYPE_CHECKING

from sentence_transformers import SentenceTransformer

if TYPE_CHECKING:
    import numpy as np

logger = logging.getLogger(__name__)

_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
_BATCH_SIZE  = 64

_model: SentenceTransformer | None = None
_model_lock = threading.Lock()


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:  # double-checked locking
                logger.info("Loading embedding model: %s", _MODEL_NAME)
                _model = SentenceTransformer(_MODEL_NAME)
                logger.info("Embedding model loaded.")
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Embed a list of strings.
    Returns list of float vectors.
    """
    if not texts:
        return []

    model = _get_model()
    vectors = model.encode(
        texts,
        batch_size=_BATCH_SIZE,
        show_progress_bar=False,
        normalize_embeddings=True,  # cosine similarity becomes dot product
        convert_to_numpy=True,
    )
    return [v.tolist() for v in vectors]


def embed_query(query: str) -> list[float]:
    """Single-query embedding (used at query time)."""
    result = embed_texts([query.strip()])
    if not result:
        raise ValueError("Empty query cannot be embedded.")
    return result[0]
