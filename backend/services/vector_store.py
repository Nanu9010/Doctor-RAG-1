"""
services/vector_store.py

Pinecone wrapper.
Namespace isolation: each document gets its own namespace = doc_id
This guarantees zero cross-document leakage per user.

Pinecone metadata stored per vector:
  {
    doc_id:      str,
    user_id:     str,
    chunk_index: int,
    page:        int,
    text:        str   ← truncated to 1000 chars (Pinecone metadata limit)
  }
"""
import os
import logging
from typing import TypedDict

from pinecone import Pinecone, ServerlessSpec

logger = logging.getLogger(__name__)

_PINECONE_API_KEY   = os.getenv("PINECONE_API_KEY", "")
_PINECONE_ENV       = os.getenv("PINECONE_ENVIRONMENT", "us-east-1")
_INDEX_NAME         = os.getenv("PINECONE_INDEX_NAME", "medrag-index")
_EMBEDDING_DIM      = int(os.getenv("EMBEDDING_DIMENSION", "384"))
_UPSERT_BATCH_SIZE  = 100

_pc    = None
_index = None


def _get_index():
    global _pc, _index
    if _index is None:
        _pc = Pinecone(api_key=_PINECONE_API_KEY)
        existing = [i.name for i in _pc.list_indexes()]
        if _INDEX_NAME not in existing:
            logger.info("Creating Pinecone index: %s", _INDEX_NAME)
            _pc.create_index(
                name=_INDEX_NAME,
                dimension=_EMBEDDING_DIM,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region=_PINECONE_ENV),
            )
        _index = _pc.Index(_INDEX_NAME)
        logger.info("Pinecone index ready: %s", _INDEX_NAME)
    return _index


class RetrievedChunk(TypedDict):
    text:        str
    page:        int
    chunk_index: int
    score:       float
    doc_id:      str


def upsert_chunks(
    doc_id:  str,
    user_id: str,
    chunks:  list[dict],   # [{text, page, chunk_index, embedding}]
) -> None:
    """
    Upsert all chunk vectors for a document.
    Vector ID format: {doc_id}#{chunk_index}
    """
    index = _get_index()
    namespace = doc_id  # one namespace per document

    vectors = []
    for chunk in chunks:
        vec_id = f"{doc_id}#{chunk['chunk_index']}"
        metadata = {
            "doc_id":      doc_id,
            "user_id":     user_id,
            "chunk_index": chunk["chunk_index"],
            "page":        chunk["page"],
            "text":        chunk["text"],
        }
        vectors.append((vec_id, chunk["embedding"], metadata))

    # Batch upsert
    for i in range(0, len(vectors), _UPSERT_BATCH_SIZE):
        batch = vectors[i : i + _UPSERT_BATCH_SIZE]
        index.upsert(vectors=batch, namespace=namespace)

    logger.info("Upserted %d vectors for doc %s", len(vectors), doc_id)


def query_document(
    doc_id:        str,
    user_id:       str,
    query_vector:  list[float],
    top_k:         int = 5,
) -> list[RetrievedChunk]:
    """
    Query ONLY within the document's namespace.
    Filters by user_id to prevent cross-user access.
    """
    index = _get_index()
    namespace = doc_id

    response = index.query(
        vector=query_vector,
        top_k=top_k,
        namespace=namespace,
        filter={"user_id": {"$eq": user_id}},
        include_metadata=True,
    )

    results: list[RetrievedChunk] = []
    for match in response.get("matches", []):
        meta = match.get("metadata", {})
        results.append(RetrievedChunk(
            text=meta.get("text", ""),
            page=meta.get("page", 0),
            chunk_index=meta.get("chunk_index", 0),
            score=round(float(match.get("score", 0.0)), 4),
            doc_id=meta.get("doc_id", doc_id),
        ))

    return results


def delete_document_vectors(doc_id: str) -> None:
    """Delete all vectors for a document (when document is deleted)."""
    index = _get_index()
    index.delete(delete_all=True, namespace=doc_id)
    logger.info("Deleted all vectors for doc %s", doc_id)
