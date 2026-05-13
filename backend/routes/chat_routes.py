"""
routes/chat_routes.py
POST /query
GET  /chat-history/<user_id>
GET  /chat-sessions/<doc_id>
GET  /chat-messages/<session_id>
"""
import uuid
import json
import logging
from flask import Blueprint, request, jsonify, g

from database.connection import get_db
from utils.auth import require_auth
from utils.validators import validate_query_text, validate_uuid
from services.rag_pipeline import run_rag_query

logger = logging.getLogger(__name__)
chat_bp = Blueprint("chat", __name__)


def _get_or_create_session(user_id: str, doc_id: str, title: str = "New Chat") -> str:
    """Return the most recent session for this user+doc, or create one."""
    with get_db() as (conn, cursor):
        cursor.execute(
            """SELECT id FROM chat_sessions
               WHERE user_id = %s AND document_id = %s
               ORDER BY updated_at DESC LIMIT 1""",
            (user_id, doc_id),
        )
        row = cursor.fetchone()
        if row:
            return row["id"]

        session_id = str(uuid.uuid4())
        cursor.execute(
            "INSERT INTO chat_sessions (id, user_id, document_id, title) VALUES (%s, %s, %s, %s)",
            (session_id, user_id, doc_id, title),
        )
        return session_id


@chat_bp.route("/query", methods=["POST"])
@require_auth
def query():
    body = request.get_json(silent=True) or {}

    try:
        doc_id = validate_uuid(body.get("doc_id", ""), "doc_id")
        query_text = validate_query_text(body.get("query", ""))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    # Verify document belongs to user and is READY
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT id, status, original_name FROM documents WHERE id = %s AND user_id = %s",
            (doc_id, g.user_id),
        )
        doc = cursor.fetchone()

    if not doc:
        return jsonify({"error": "Document not found."}), 404
    if doc["status"] != "READY":
        return jsonify({
            "error": f"Document is not ready for queries. Current status: {doc['status']}",
            "status": doc["status"],
        }), 409

    # Run RAG
    try:
        rag_response = run_rag_query(
            query=query_text,
            doc_id=doc_id,
            user_id=g.user_id,
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        logger.error("RAG pipeline error: %s", e)
        return jsonify({"error": "LLM service temporarily unavailable. Please retry."}), 503

    # Persist messages
    session_id = _get_or_create_session(
        g.user_id, doc_id,
        title=query_text[:80],
    )
    user_msg_id = str(uuid.uuid4())
    bot_msg_id  = str(uuid.uuid4())

    with get_db() as (conn, cursor):
        # Update session timestamp
        cursor.execute(
            "UPDATE chat_sessions SET updated_at = NOW() WHERE id = %s", (session_id,)
        )
        # Store user message
        cursor.execute(
            """INSERT INTO chat_messages
               (id, session_id, user_id, role, content)
               VALUES (%s, %s, %s, 'user', %s)""",
            (user_msg_id, session_id, g.user_id, query_text),
        )
        # Store assistant message
        cursor.execute(
            """INSERT INTO chat_messages
               (id, session_id, user_id, role, content, source_chunks, confidence, tokens_used)
               VALUES (%s, %s, %s, 'assistant', %s, %s, %s, %s)""",
            (
                bot_msg_id, session_id, g.user_id,
                rag_response["answer"],
                json.dumps(rag_response["source_chunks"]),
                rag_response["confidence"],
                rag_response["tokens_used"],
            ),
        )

    return jsonify({
        "answer":       rag_response["answer"],
        "confidence":   rag_response["confidence"],
        "source_chunks": rag_response["source_chunks"],
        "session_id":   session_id,
        "doc_name":     doc["original_name"],
    }), 200


@chat_bp.route("/chat-history/<target_user_id>", methods=["GET"])
@require_auth
def chat_history(target_user_id: str):
    # Users can only access their own history
    if target_user_id != g.user_id:
        return jsonify({"error": "Access denied."}), 403

    with get_db() as (conn, cursor):
        cursor.execute(
            """SELECT cs.id AS session_id, cs.title, cs.created_at, cs.updated_at,
                      d.id AS doc_id, d.original_name AS doc_name, d.status AS doc_status
               FROM chat_sessions cs
               JOIN documents d ON d.id = cs.document_id
               WHERE cs.user_id = %s
               ORDER BY cs.updated_at DESC""",
            (g.user_id,),
        )
        sessions = cursor.fetchall()

    return jsonify([
        {
            "session_id":  s["session_id"],
            "title":       s["title"],
            "doc_id":      s["doc_id"],
            "doc_name":    s["doc_name"],
            "doc_status":  s["doc_status"],
            "created_at":  s["created_at"].isoformat() if s["created_at"] else None,
            "updated_at":  s["updated_at"].isoformat() if s["updated_at"] else None,
        }
        for s in sessions
    ]), 200


@chat_bp.route("/chat-messages/<session_id>", methods=["GET"])
@require_auth
def chat_messages(session_id: str):
    try:
        validate_uuid(session_id, "session_id")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    # Verify ownership
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT id FROM chat_sessions WHERE id = %s AND user_id = %s",
            (session_id, g.user_id),
        )
        if not cursor.fetchone():
            return jsonify({"error": "Session not found."}), 404

        cursor.execute(
            """SELECT id, role, content, source_chunks, confidence, created_at
               FROM chat_messages
               WHERE session_id = %s
               ORDER BY created_at ASC""",
            (session_id,),
        )
        messages = cursor.fetchall()

    return jsonify([
        {
            "id":           m["id"],
            "role":         m["role"],
            "content":      m["content"],
            "source_chunks": json.loads(m["source_chunks"]) if m["source_chunks"] else [],
            "confidence":   m["confidence"],
            "created_at":   m["created_at"].isoformat() if m["created_at"] else None,
        }
        for m in messages
    ]), 200

