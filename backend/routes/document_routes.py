"""
routes/document_routes.py
POST /upload
GET  /status/<doc_id>
GET  /documents          (list user's documents)
DELETE /documents/<doc_id>
"""
import os
import uuid
import logging
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify, g

from database.connection import get_db
from utils.auth import require_auth
from utils.validators import validate_upload_file, validate_uuid
from services.processing_worker import submit_document_for_processing
from services.vector_store import delete_document_vectors

logger = logging.getLogger(__name__)
document_bp = Blueprint("documents", __name__)

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@document_bp.route("/upload", methods=["POST"])
@require_auth
def upload_document():
    if "file" not in request.files:
        return jsonify({"error": "No file part in request."}), 400

    file = request.files["file"]
    try:
        validate_upload_file(file)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    doc_id    = str(uuid.uuid4())
    safe_name = secure_filename(file.filename)
    stored_name = f"{doc_id}_{safe_name}"
    file_path = os.path.join(UPLOAD_DIR, stored_name)

    # Check file size (stream to disk)
    max_bytes = int(os.getenv("MAX_UPLOAD_MB", "50")) * 1024 * 1024
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > max_bytes:
        return jsonify({"error": f"File exceeds {os.getenv('MAX_UPLOAD_MB', 50)}MB limit."}), 413

    file.save(file_path)

    with get_db() as (conn, cursor):
        cursor.execute(
            """INSERT INTO documents
               (id, user_id, filename, original_name, file_path, file_size, status)
               VALUES (%s, %s, %s, %s, %s, %s, 'UPLOADED')""",
            (doc_id, g.user_id, stored_name, safe_name, file_path, size),
        )

    # Fire async processing — non-blocking
    submit_document_for_processing(doc_id, g.user_id, file_path)

    return jsonify({
        "doc_id":   doc_id,
        "filename": safe_name,
        "status":   "UPLOADED",
        "message":  "Document uploaded. Processing started.",
    }), 202


@document_bp.route("/status/<doc_id>", methods=["GET"])
@require_auth
def get_status(doc_id: str):
    try:
        validate_uuid(doc_id, "doc_id")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    with get_db() as (conn, cursor):
        cursor.execute(
            """SELECT id, status, error_message, chunk_count, page_count,
                      ocr_used, original_name, created_at, updated_at
               FROM documents
               WHERE id = %s AND user_id = %s""",
            (doc_id, g.user_id),
        )
        doc = cursor.fetchone()

    if not doc:
        return jsonify({"error": "Document not found."}), 404

    return jsonify({
        "doc_id":       doc["id"],
        "status":       doc["status"],
        "filename":     doc["original_name"],
        "page_count":   doc["page_count"],
        "chunk_count":  doc["chunk_count"],
        "ocr_used":     bool(doc["ocr_used"]),
        "error":        doc["error_message"],
        "created_at":   doc["created_at"].isoformat() if doc["created_at"] else None,
        "updated_at":   doc["updated_at"].isoformat() if doc["updated_at"] else None,
    }), 200


@document_bp.route("/documents", methods=["GET"])
@require_auth
def list_documents():
    with get_db() as (conn, cursor):
        cursor.execute(
            """SELECT id, original_name, status, page_count, chunk_count,
                      ocr_used, created_at
               FROM documents
               WHERE user_id = %s
               ORDER BY created_at DESC""",
            (g.user_id,),
        )
        docs = cursor.fetchall()

    return jsonify([
        {
            "doc_id":      d["id"],
            "filename":    d["original_name"],
            "status":      d["status"],
            "page_count":  d["page_count"],
            "chunk_count": d["chunk_count"],
            "ocr_used":    bool(d["ocr_used"]),
            "created_at":  d["created_at"].isoformat() if d["created_at"] else None,
        }
        for d in docs
    ]), 200


@document_bp.route("/documents/<doc_id>", methods=["DELETE"])
@require_auth
def delete_document(doc_id: str):
    try:
        validate_uuid(doc_id, "doc_id")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT id, file_path FROM documents WHERE id = %s AND user_id = %s",
            (doc_id, g.user_id),
        )
        doc = cursor.fetchone()

    if not doc:
        return jsonify({"error": "Document not found."}), 404

    # Delete from Pinecone
    try:
        delete_document_vectors(doc_id)
    except Exception as e:
        logger.error("Failed to delete Pinecone vectors for doc %s: %s", doc_id, e)

    # Delete file
    try:
        if os.path.exists(doc["file_path"]):
            os.remove(doc["file_path"])
    except OSError as e:
        logger.warning("Could not remove file %s: %s", doc["file_path"], e)

    # Delete DB record (cascades to sessions + messages)
    with get_db() as (conn, cursor):
        cursor.execute(
            "DELETE FROM documents WHERE id = %s AND user_id = %s",
            (doc_id, g.user_id),
        )

    return jsonify({"message": "Document deleted."}), 200

@document_bp.route("/documents/<doc_id>", methods=["PUT"])
@require_auth
def rename_document(doc_id: str):
    try:
        validate_uuid(doc_id, "doc_id")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    data = request.get_json()
    new_name = data.get("filename") if data else None
    if not new_name or not new_name.strip():
        return jsonify({"error": "New filename is required."}), 400

    new_name = new_name.strip()
    if not new_name.endswith('.pdf'):
        new_name += '.pdf'

    with get_db() as (conn, cursor):
        cursor.execute(
            "UPDATE documents SET original_name = %s WHERE id = %s AND user_id = %s",
            (new_name, doc_id, g.user_id),
        )
        if cursor.rowcount == 0:
            return jsonify({"error": "Document not found."}), 404

    return jsonify({"message": "Document renamed.", "filename": new_name}), 200

