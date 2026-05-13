"""
routes/auth_routes.py
POST /auth/register
POST /auth/login
"""
import uuid
import logging
from flask import Blueprint, request, jsonify

from database.connection import get_db
from utils.auth import hash_password, verify_password, generate_token
from utils.validators import validate_email, validate_password, validate_name

logger = logging.getLogger(__name__)
auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/register", methods=["POST"])
def register():
    body = request.get_json(silent=True) or {}
    try:
        email    = validate_email(body.get("email", ""))
        password = body.get("password", "")
        validate_password(password)
        name = validate_name(body.get("name", ""))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    with get_db() as (conn, cursor):
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            return jsonify({"error": "Email already registered."}), 409

        user_id      = str(uuid.uuid4())
        hashed_pass  = hash_password(password)
        cursor.execute(
            "INSERT INTO users (id, email, name, password) VALUES (%s, %s, %s, %s)",
            (user_id, email, name, hashed_pass),
        )

    token = generate_token(user_id)
    return jsonify({"token": token, "user_id": user_id, "name": name}), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    body = request.get_json(silent=True) or {}
    try:
        email    = validate_email(body.get("email", ""))
        password = body.get("password", "")
        if not password:
            raise ValueError("Password required.")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT id, name, password FROM users WHERE email = %s", (email,)
        )
        user = cursor.fetchone()

    if not user or not verify_password(password, user["password"]):
        return jsonify({"error": "Invalid email or password."}), 401

    token = generate_token(user["id"])
    return jsonify({"token": token, "user_id": user["id"], "name": user["name"]}), 200
