"""
utils/validators.py
Centralised input validation. Keep validation out of route handlers.
"""
import os
import re

ALLOWED_MIME_TYPES = {"application/pdf"}
ALLOWED_EXTENSIONS = {".pdf"}
MAX_UPLOAD_BYTES   = int(os.getenv("MAX_UPLOAD_MB", "50")) * 1024 * 1024

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def validate_email(email: str) -> str:
    email = email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise ValueError("Invalid email address.")
    if len(email) > 255:
        raise ValueError("Email too long.")
    return email


def validate_password(password: str) -> None:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    if len(password) > 128:
        raise ValueError("Password too long.")


def validate_name(name: str) -> str:
    name = name.strip()
    if not name or len(name) < 2:
        raise ValueError("Name must be at least 2 characters.")
    if len(name) > 255:
        raise ValueError("Name too long.")
    return name


def validate_upload_file(file) -> None:
    """Validate a Werkzeug FileStorage object."""
    if not file or not file.filename:
        raise ValueError("No file provided.")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Only PDF files are accepted. Got: {ext or 'unknown'}")

    # Read first 4 bytes for PDF magic number check
    header = file.read(4)
    file.seek(0)
    if header != b"%PDF":
        raise ValueError("File does not appear to be a valid PDF.")


def validate_query_text(query: str) -> str:
    query = query.strip()
    if not query:
        raise ValueError("Query cannot be empty.")
    if len(query) > 2000:
        raise ValueError("Query exceeds 2000 character limit.")
    return query


def validate_uuid(value: str, field_name: str = "id") -> str:
    import uuid as _uuid
    try:
        _uuid.UUID(str(value))
    except (ValueError, AttributeError):
        raise ValueError(f"Invalid {field_name}: must be a UUID.")
    return str(value)
