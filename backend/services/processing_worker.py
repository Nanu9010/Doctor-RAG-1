"""
services/processing_worker.py

Background thread pool for async document processing.
No Celery dependency — ThreadPoolExecutor is sufficient for
moderate load. For high scale, swap in Celery + Redis.

Retry logic: up to MAX_ATTEMPTS per job, exponential backoff.
"""
import os
import uuid
import logging
import time
import threading
from concurrent.futures import ThreadPoolExecutor

from database.connection import get_db
from services.document_processor import process_document, DocumentProcessingError
from services.embedding_service import embed_texts
from services.vector_store import upsert_chunks

logger = logging.getLogger(__name__)

_MAX_WORKERS  = int(os.getenv("WORKER_THREADS", "4"))
_MAX_ATTEMPTS = 3
_RETRY_DELAY  = 5  # seconds base; multiplied by attempt number

_executor = ThreadPoolExecutor(max_workers=_MAX_WORKERS, thread_name_prefix="doc-worker")


# ── Status helpers ────────────────────────────────────────────────────────────

def _set_doc_status(doc_id: str, status: str, error: str | None = None,
                    chunk_count: int | None = None, page_count: int | None = None,
                    ocr_used: bool | None = None) -> None:
    updates = ["status = %s", "updated_at = NOW()"]
    params: list = [status]

    if error is not None:
        updates.append("error_message = %s")
        params.append(error[:2048])
    if chunk_count is not None:
        updates.append("chunk_count = %s")
        params.append(chunk_count)
    if page_count is not None:
        updates.append("page_count = %s")
        params.append(page_count)
    if ocr_used is not None:
        updates.append("ocr_used = %s")
        params.append(int(ocr_used))

    params.append(doc_id)
    sql = f"UPDATE documents SET {', '.join(updates)} WHERE id = %s"
    with get_db() as (conn, cursor):
        cursor.execute(sql, params)


def _record_job(doc_id: str) -> str:
    job_id = str(uuid.uuid4())
    with get_db() as (conn, cursor):
        cursor.execute(
            "INSERT INTO processing_jobs (id, document_id) VALUES (%s, %s)",
            (job_id, doc_id),
        )
    return job_id


def _update_job_attempt(job_id: str, error: str | None = None) -> None:
    with get_db() as (conn, cursor):
        if error:
            cursor.execute(
                "UPDATE processing_jobs SET attempts = attempts + 1, last_error = %s, "
                "updated_at = NOW() WHERE id = %s",
                (error[:2048], job_id),
            )
        else:
            cursor.execute(
                "UPDATE processing_jobs SET attempts = attempts + 1, updated_at = NOW() WHERE id = %s",
                (job_id,),
            )


def _get_job_attempts(job_id: str) -> int:
    with get_db() as (conn, cursor):
        cursor.execute("SELECT attempts FROM processing_jobs WHERE id = %s", (job_id,))
        row = cursor.fetchone()
        return row["attempts"] if row else 0


# ── Core processing task ──────────────────────────────────────────────────────

def _process_task(doc_id: str, user_id: str, file_path: str, job_id: str) -> None:
    attempt = 0
    while attempt < _MAX_ATTEMPTS:
        attempt += 1
        _update_job_attempt(job_id)
        logger.info("Processing doc %s — attempt %d/%d", doc_id, attempt, _MAX_ATTEMPTS)

        try:
            _set_doc_status(doc_id, "PROCESSING")

            # 1. Extract + chunk
            result = process_document(file_path)
            chunks = result["chunks"]

            # 2. Embed all chunks in batch
            texts      = [c.text for c in chunks]
            embeddings = embed_texts(texts)

            # 3. Build payload
            chunk_payloads = [
                {
                    "text":        chunks[i].text,
                    "page":        chunks[i].page,
                    "chunk_index": chunks[i].chunk_index,
                    "embedding":   embeddings[i],
                }
                for i in range(len(chunks))
            ]

            # 4. Upsert to Pinecone
            upsert_chunks(doc_id=doc_id, user_id=user_id, chunks=chunk_payloads)

            # 5. Mark READY
            _set_doc_status(
                doc_id, "READY",
                chunk_count=len(chunks),
                page_count=result["page_count"],
                ocr_used=result["ocr_used"],
            )
            logger.info("Doc %s processing complete — %d chunks", doc_id, len(chunks))
            return  # success

        except DocumentProcessingError as e:
            # Non-retriable: bad document
            error_msg = str(e)
            logger.warning("Doc %s permanently failed: %s", doc_id, error_msg)
            _set_doc_status(doc_id, "FAILED", error=error_msg)
            _update_job_attempt(job_id, error=error_msg)
            return

        except Exception as e:
            error_msg = str(e)
            logger.error("Doc %s attempt %d failed: %s", doc_id, attempt, error_msg)
            _update_job_attempt(job_id, error=error_msg)

            if attempt < _MAX_ATTEMPTS:
                sleep_time = _RETRY_DELAY * attempt
                logger.info("Retrying doc %s in %ds", doc_id, sleep_time)
                time.sleep(sleep_time)
            else:
                _set_doc_status(doc_id, "FAILED", error=f"Failed after {_MAX_ATTEMPTS} attempts: {error_msg}")


# ── Public API ────────────────────────────────────────────────────────────────

def submit_document_for_processing(doc_id: str, user_id: str, file_path: str) -> str:
    """
    Submit a document to the background processing queue.
    Returns job_id for tracking.
    Non-blocking.
    """
    job_id = _record_job(doc_id)
    _executor.submit(_process_task, doc_id, user_id, file_path, job_id)
    logger.info("Submitted doc %s to processing queue (job %s)", doc_id, job_id)
    return job_id
