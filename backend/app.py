"""
app.py — Flask application factory.

Run locally:
    python app.py

Run production:
    gunicorn -w 4 -b 0.0.0.0:5000 app:create_app()
"""
import os
import logging
from dotenv import load_dotenv

load_dotenv()  # Must be before any os.getenv calls

from flask import Flask, jsonify, send_from_directory, send_file
from flask_cors import CORS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# Resolve frontend directory relative to this file
_BACKEND_DIR  = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)
_FRONTEND_DIR = os.path.join(_PROJECT_ROOT, "frontend")


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)
    app.secret_key = os.getenv("FLASK_SECRET_KEY", "insecure-dev-secret")

    # CORS: in prod, restrict origins to your domain
    CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

    # ── Register blueprints ───────────────────────────────────────────────────
    from routes.auth_routes     import auth_bp
    from routes.document_routes import document_bp
    from routes.chat_routes     import chat_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(document_bp)
    app.register_blueprint(chat_bp)

    # ── Health check ──────────────────────────────────────────────────────────
    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "service": "MedRAG API"}), 200

    # ── Serve Frontend Static Files ───────────────────────────────────────────
    @app.route("/", methods=["GET"])
    def index():
        return send_file(os.path.join(_FRONTEND_DIR, "index.html"))

    @app.route("/css/<path:filename>", methods=["GET"])
    def serve_css(filename):
        return send_from_directory(os.path.join(_FRONTEND_DIR, "css"), filename)

    @app.route("/js/<path:filename>", methods=["GET"])
    def serve_js(filename):
        return send_from_directory(os.path.join(_FRONTEND_DIR, "js"), filename)

    @app.route("/clinical_app.html", methods=["GET"])
    def serve_clinical_app():
        return send_file(os.path.join(_FRONTEND_DIR, "clinical_app.html"))

    # ── Global error handlers ─────────────────────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Endpoint not found."}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"error": "Method not allowed."}), 405

    @app.errorhandler(413)
    def payload_too_large(e):
        return jsonify({"error": "File too large."}), 413

    @app.errorhandler(500)
    def internal_error(e):
        logger.exception("Unhandled internal error")
        return jsonify({"error": "Internal server error."}), 500

    # Prevent uploads from blocking: set max content length
    max_mb = int(os.getenv("MAX_UPLOAD_MB", "50"))
    app.config["MAX_CONTENT_LENGTH"] = max_mb * 1024 * 1024

    logger.info("MedRAG Flask app created. Frontend dir: %s", _FRONTEND_DIR)
    return app


if __name__ == "__main__":
    application = create_app()
    application.run(host="0.0.0.0", port=5000, debug=False)

