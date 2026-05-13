"""
utils/auth.py
JWT-based stateless auth. Tokens expire in 24h.
"""
import os
import uuid
import hmac
import hashlib
import base64
import json
import time
from functools import wraps
from flask import request, jsonify, g
import bcrypt


_JWT_SECRET = os.getenv("JWT_SECRET", "insecure-default-change-me").encode()
_TOKEN_TTL = 86400  # 24 hours


# ── Password helpers ──────────────────────────────────────────────────────────

def hash_password(plaintext: str) -> str:
    return bcrypt.hashpw(plaintext.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(plaintext: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plaintext.encode(), hashed.encode())
    except Exception:
        return False


# ── Minimal JWT (no external library dependency) ──────────────────────────────

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * (padding % 4))


def generate_token(user_id: str) -> str:
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url_encode(json.dumps({
        "sub": user_id,
        "iat": int(time.time()),
        "exp": int(time.time()) + _TOKEN_TTL,
    }).encode())
    sig_input = f"{header}.{payload}".encode()
    sig = _b64url_encode(hmac.new(_JWT_SECRET, sig_input, hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"


def decode_token(token: str) -> dict | None:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header, payload, sig = parts
        sig_input = f"{header}.{payload}".encode()
        expected_sig = _b64url_encode(
            hmac.new(_JWT_SECRET, sig_input, hashlib.sha256).digest()
        )
        if not hmac.compare_digest(sig, expected_sig):
            return None
        claims = json.loads(_b64url_decode(payload))
        if claims.get("exp", 0) < time.time():
            return None
        return claims
    except Exception:
        return None


# ── Flask decorator ───────────────────────────────────────────────────────────

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401
        token = auth_header.split(" ", 1)[1]
        claims = decode_token(token)
        if not claims:
            return jsonify({"error": "Invalid or expired token"}), 401
        g.user_id = claims["sub"]
        return f(*args, **kwargs)
    return decorated
