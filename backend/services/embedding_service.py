"""
services/embedding_service.py

Production embedding using Google Gemini text-embedding-004 API.
Replaces sentence-transformers to eliminate the 800MB+ PyTorch dependency
which exceeded Vercel's 500MB Lambda bundle limit.

Model: gemini-embedding-2 (768 dims default, configurable via EMBEDDING_DIMENSION)
Task types:
  - embed_texts()  → "retrieval_document" (for indexing chunks)
  - embed_query()  → "retrieval_query"    (for query-time search)
"""
import os
import logging
from typing import List

logger = logging.getLogger(__name__)

_GEMINI_API_KEY    = os.getenv("GEMINI_API_KEY", "")
_EMBEDDING_MODEL   = os.getenv("GEMINI_EMBEDDING_MODEL", "models/gemini-embedding-2")
_OUTPUT_DIM        = int(os.getenv("EMBEDDING_DIMENSION", "768"))

# Lazy import — only load if embedding is needed (faster cold starts)
_genai = None


def _get_genai():
    global _genai
    if _genai is None:
        try:
            import google.generativeai as genai
            genai.configure(api_key=_GEMINI_API_KEY)
            _genai = genai
            logger.info("Gemini embedding client initialized (model: %s, dim: %d)",
                        _EMBEDDING_MODEL, _OUTPUT_DIM)
        except ImportError:
            raise RuntimeError(
                "google-generativeai not installed. Run: pip install google-generativeai"
            )
    return _genai


def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Embed a batch of document chunks for indexing.
    Returns list of float vectors, one per input text.
    """
    if not texts:
        return []

    genai = _get_genai()
    results = []

    # Gemini embed_content handles one string at a time efficiently;
    # batch in groups of 20 to stay within API limits
    batch_size = 20
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        for text in batch:
            resp = genai.embed_content(
                model=_EMBEDDING_MODEL,
                content=text.strip(),
                task_type="retrieval_document",
                output_dimensionality=_OUTPUT_DIM,
            )
            results.append(resp["embedding"])

    logger.debug("Embedded %d texts via Gemini", len(results))
    return results


def embed_query(query: str) -> List[float]:
    """
    Embed a single user query for similarity search.
    Uses 'retrieval_query' task type (asymmetric retrieval).
    """
    query = query.strip()
    if not query:
        raise ValueError("Empty query cannot be embedded.")

    genai = _get_genai()
    resp = genai.embed_content(
        model=_EMBEDDING_MODEL,
        content=query,
        task_type="retrieval_query",
        output_dimensionality=_OUTPUT_DIM,
    )
    return resp["embedding"]
