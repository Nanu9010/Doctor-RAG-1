"""
api/index.py — Vercel Serverless Entry Point for MedRAG

This file is the WSGI adapter that Vercel's Python runtime uses.
It imports the Flask app from the backend directory and exposes it.

Note on serverless constraints:
- File uploads are stored in /tmp (ephemeral, max 512MB)
- Background ThreadPoolExecutor works within a single function invocation
  but state doesn't persist across cold starts
- For production scale, use a managed queue (SQS, Cloud Tasks) instead
"""
import sys
import os

# Add backend directory to Python path so all imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

# Override UPLOAD_DIR to use /tmp on serverless (only writable path on Vercel)
os.environ.setdefault('UPLOAD_DIR', '/tmp/medrag_uploads')

from app import create_app

# Vercel looks for `app` as the WSGI callable
app = create_app()

# Vercel Python runtime also accepts `handler` 
# The runtime auto-discovers `app` if it's a WSGI callable
