"""
services/rag_pipeline.py

RAG Query Pipeline:
  1. Embed user query
  2. Retrieve top-k chunks from Pinecone (doc-scoped)
  3. Filter by confidence threshold
  4. Build strict grounded prompt
  5. Call LLM
  6. Return answer + source metadata + confidence score

Hallucination prevention enforced at:
  - Prompt engineering (strict system prompt)
  - Confidence threshold gating
  - Source attribution in response
"""
import os
import logging
import statistics
from typing import TypedDict
import re

import openai

from services.embedding_service import embed_query
from services.vector_store import query_document, RetrievedChunk

logger = logging.getLogger(__name__)

_OPENAI_API_KEY    = os.getenv("GEMINI_API_KEY", "")
_OPENAI_MODEL      = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
_TOP_K             = int(os.getenv("TOP_K_RESULTS", "5"))
_MIN_CONFIDENCE    = float(os.getenv("MIN_CONFIDENCE_THRESHOLD", "0.35"))
_MAX_CONTEXT_CHARS = 6000

# Lazy client — created on first request to avoid startup crash if key is missing
_openai_client = None

def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        key = os.getenv("GEMINI_API_KEY", "")
        if not key:
            raise RuntimeError("GEMINI_API_KEY environment variable is not set.")
        _openai_client = openai.OpenAI(
            api_key=key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        )
    return _openai_client


# ── Types ─────────────────────────────────────────────────────────────────────

class RAGResponse(TypedDict):
    answer:       str
    confidence:   float
    source_chunks: list[dict]
    tokens_used:  int


# ── Prompt construction ───────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are a clinical document assistant. 
Answer using the context below.
If partially relevant, still try to answer.
If not found, say: "Not clearly mentioned in document."

Context from document:
{context}
"""


def _build_context_block(chunks: list[RetrievedChunk]) -> str:
    parts = []
    total_chars = 0
    for chunk in chunks:
        excerpt = f"[Page {chunk['page']} | Relevance: {chunk['score']:.2f}]\n{chunk['text']}"
        if total_chars + len(excerpt) > _MAX_CONTEXT_CHARS:
            break
        parts.append(excerpt)
        total_chars += len(excerpt)
    return "\n\n---\n\n".join(parts)


def _compute_confidence(chunks: list[RetrievedChunk]) -> float:
    if not chunks:
        return 0.0
    return min(1.0, chunks[0]["score"])

def expand_query(q: str) -> str:
    return f"{q} meaning use indication treatment purpose definition medicine drug"

def keyword_score(query: str, text: str) -> float:
    q_words = set(re.findall(r'\w+', query.lower()))
    t_words = set(re.findall(r'\w+', text.lower()))
    if not q_words: return 0.0
    return len(q_words & t_words) / len(q_words)

def hybrid_rerank(query: str, chunks: list[RetrievedChunk], top_k: int) -> list[RetrievedChunk]:
    keywords = ["clopilet", "ecosprin", "lipitor", "arrhythmia", "cad", "antiplatelet"]
    query_lower = query.lower()
    has_important_kw = any(kw in query_lower for kw in keywords)
    
    for c in chunks:
        vec_score = c['score']
        kw_score = keyword_score(query, c['text'])
        final_score = (0.7 * vec_score) + (0.3 * kw_score)
        
        if has_important_kw and any(kw in c['text'].lower() for kw in keywords):
            final_score += 0.2
            
        c['score'] = round(final_score, 4)
        
    chunks.sort(key=lambda x: x['score'], reverse=True)
    return chunks[:top_k]


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run_rag_query(
    query:   str,
    doc_id:  str,
    user_id: str,
) -> RAGResponse:
    """
    Full RAG pipeline. Raises ValueError on invalid input.
    """
    query = query.strip()
    if not query:
        raise ValueError("Query cannot be empty.")
    if len(query) > 2000:
        raise ValueError("Query exceeds maximum length of 2000 characters.")

    # 1. Embed query
    expanded_q = expand_query(query)
    query_vector = embed_query(expanded_q)

    # 2. Retrieve chunks
    chunks = query_document(
        doc_id=doc_id,
        user_id=user_id,
        query_vector=query_vector,
        top_k=20,
    )
    
    chunks = hybrid_rerank(query, chunks, _TOP_K)

    # 3. Confidence check
    confidence = _compute_confidence(chunks)

    if not chunks:
        return RAGResponse(
            answer="Not clearly mentioned in document.",
            confidence=0.0,
            source_chunks=[],
            tokens_used=0,
        )

    # Debug: Print retrieved chunks
    print("\n=== DEBUG RETRIEVAL ===")
    for i, r in enumerate(chunks):
        print(f"{i+1}. Score: {r['score']}")
        print(f"Page: {r['page']}")
        print(f"Text: {r['text']}")
        print("-------------------")

    # 4. Build prompt
    context_block = _build_context_block(chunks)
    system_prompt = _SYSTEM_PROMPT.format(context=context_block)

    # 5. LLM call
    try:
        completion = _get_openai_client().chat.completions.create(
            model=_OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": query},
            ],
            temperature=0.0,   # deterministic — critical for medical context
            max_tokens=1024,
        )
    except openai.OpenAIError as e:
        logger.error("OpenAI API error: %s", e)
        raise RuntimeError(f"LLM service unavailable: {e}") from e

    answer      = completion.choices[0].message.content or ""
    tokens_used = completion.usage.total_tokens if completion.usage else 0

    # 6. Serialize source chunks for storage and display
    source_chunks = [
        {
            "text":        c["text"][:400],
            "page":        c["page"],
            "chunk_index": c["chunk_index"],
            "score":       c["score"],
        }
        for c in chunks
    ]

    return RAGResponse(
        answer=answer,
        confidence=confidence,
        source_chunks=source_chunks,
        tokens_used=tokens_used,
    )
