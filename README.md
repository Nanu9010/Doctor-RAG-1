# MedRAG — Clinical Document Assistant
Production-ready RAG system for medical document Q&A.

## Architecture

```
User → Frontend (HTML/JS)
         ↓ REST
     Flask API
    ┌────┼────────────────────┐
    │    ↓                   ↓
  MySQL               Background Worker
  (users,             ┌──────────────┐
   docs,              │ PyMuPDF/OCR  │
   chats)             │ Chunking     │
    ↑                 │ Embeddings   │
    │                 │ Pinecone     │
    └────── RAG ──────┘
    Query → embed → Pinecone → context → OpenAI → answer
```

## Folder Structure

```
medrag/
├── backend/
│   ├── app.py                      # Flask factory
│   ├── requirements.txt
│   ├── .env.example
│   ├── routes/
│   │   ├── auth_routes.py          # POST /auth/register, /auth/login
│   │   ├── document_routes.py      # POST /upload, GET /status, /documents
│   │   └── chat_routes.py          # POST /query, GET /chat-history
│   ├── services/
│   │   ├── document_processor.py   # PDF→chunks (PyMuPDF + Tesseract)
│   │   ├── embedding_service.py    # sentence-transformers singleton
│   │   ├── vector_store.py         # Pinecone CRUD
│   │   ├── rag_pipeline.py         # embed→retrieve→prompt→LLM
│   │   └── processing_worker.py    # ThreadPoolExecutor + retry
│   ├── utils/
│   │   ├── auth.py                 # JWT + bcrypt
│   │   └── validators.py           # Input validation
│   └── database/
│       └── connection.py           # MySQL connection pool
├── frontend/
│   └── index.html                  # Complete SPA (HTML/CSS/JS)
└── database/
    └── schema.sql                  # MySQL DDL
```

## Local Setup

### 1. Prerequisites

```bash
# System dependencies
sudo apt-get install -y tesseract-ocr mysql-server

# Python 3.11+
python --version
```

### 2. Database

```bash
mysql -u root -p < database/schema.sql
```

### 3. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env — fill in:
#   DB_PASSWORD, PINECONE_API_KEY, OPENAI_API_KEY
#   FLASK_SECRET_KEY, JWT_SECRET (generate with: python -c "import secrets; print(secrets.token_hex(32))")

python app.py
# → running on http://localhost:5000
```

### 4. Pinecone Setup

1. Sign up at pinecone.io (free tier: 1 index)
2. Create a project → get API key
3. Set `PINECONE_API_KEY` in `.env`
4. The index is auto-created on first run with dimension=384

### 5. OpenAI

1. Get API key from platform.openai.com
2. Set `OPENAI_API_KEY` in `.env`
3. Default model: `gpt-4o-mini` (cheap, fast, accurate)

### 6. Frontend

```bash
# Serve from any static file server
cd frontend
python -m http.server 8080
# → open http://localhost:8080
```

## API Reference

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | /auth/register | No | Create account |
| POST | /auth/login | No | Get JWT token |
| POST | /upload | Bearer | Upload PDF |
| GET | /status/:doc_id | Bearer | Poll processing status |
| GET | /documents | Bearer | List user's documents |
| DELETE | /documents/:doc_id | Bearer | Delete document |
| POST | /query | Bearer | RAG query |
| GET | /chat-history/:user_id | Bearer | All sessions |
| GET | /chat-messages/:session_id | Bearer | Messages in session |
| GET | /health | No | Healthcheck |

## Security Notes

- JWT tokens expire in 24 hours
- Each document stored in its own Pinecone namespace
- All queries filter by user_id — cross-user access impossible
- File type validated by magic bytes, not just extension
- Passwords hashed with bcrypt (rounds=12)
- SQL uses parameterized queries throughout
- Input length limits on all fields

## Scaling Notes

- Swap ThreadPoolExecutor → Celery + Redis for >100 concurrent uploads
- Add Redis caching for embedding lookups
- Use Gunicorn with 4+ workers in production
- Add rate limiting (Flask-Limiter) before exposing publicly
- Medical deployments require HIPAA-compliant hosting

## Free Alternatives to OpenAI

Set in `.env`:
```
OPENAI_API_KEY=your_mistral_api_key   # from console.mistral.ai
OPENAI_MODEL=mistral-small-latest
```
And in `rag_pipeline.py`, update the base_url:
```python
openai_client = openai.OpenAI(
    api_key=_OPENAI_API_KEY,
    base_url="https://api.mistral.ai/v1"
)
```
# Doctor-RAG-1
