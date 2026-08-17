# RAG PDF Q&A — Backend

FastAPI backend for a fully local, free, open-source RAG PDF Q&A system with **JWT authentication and per-user data isolation**.

**Stack:** FastAPI · SQLAlchemy + Alembic · SQLite · sentence-transformers (`BAAI/bge-small-en-v1.5`, local CPU) · ChromaDB (persistent local) · Ollama (local LLM) · pdfplumber · bcrypt + PyJWT

No API keys, no paid services.

## Prerequisites

1. **Ollama** — install from https://ollama.com, then pull a model:
   ```bash
   ollama pull gemma4        # or llama3, mistral, qwen2.5
   ollama list               # verify the model is present
   curl http://localhost:11434   # verify the server is running
   ```
2. **Python 3.11+** with `venv`.

## Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt   # or: pip install -e ".[dev]"
cp .env.example .env              # adjust SECRET_KEY for anything non-local
alembic upgrade head              # create/upgrade the DB schema
```

## Run

```bash
uvicorn app.main:app --reload
```

- Server → http://localhost:8000
- Interactive docs → http://localhost:8000/docs (use **Authorize** with the credentials from login)
- `--reload` is dev-only; production runs `uvicorn app.main:app` with a worker manager.

## Configuration (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | dev value | JWT signing key — **change in production** (`python -c "import secrets; print(secrets.token_urlsafe(64))"`) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 1440 | Token lifetime |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server |
| `OLLAMA_MODEL` | `gemma4` | LLM model |
| `MAX_UPLOAD_MB` | 50 | Upload size cap (413 above this) |
| `CORS_ORIGINS` | `["*"]` | Comma-separated list in production |

## API (all under `/api/v1`)

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/register` | — | Create account → `{access_token, user}` (201; 409 if email exists) |
| POST | `/auth/login` | — | OAuth2 form login → `{access_token, user}` (401 on bad creds) |
| GET | `/auth/me` | Bearer | Current user |
| POST | `/upload` | Bearer | Upload PDF (multipart). Returns `{doc_id, filename, status}` immediately; processing runs in the background |
| GET | `/documents/{doc_id}/status` | Bearer | Poll `processing` → `ready` / `failed` |
| GET | `/documents` | Bearer | List the **current user's** documents |
| DELETE | `/documents/{doc_id}` | Bearer | Delete PDF file, DB record, and Chroma collection |
| POST | `/query` | Bearer | RAG question: `{doc_id, question, conversation_id?}` → `{answer, sources, conversation_id}` |
| GET | `/conversations/{doc_id}` | Bearer | Chat history grouped by conversation |

**Isolation model:** every document endpoint filters by `Document.user_id == current_user.id`. Foreign documents return **404** (never reveal existence). Conversations inherit isolation through their document.

## Project structure

```
app/
├── main.py            # app factory: CORS, middleware, /api/v1 wiring, /health
├── core/              # config.py (pydantic-settings) · security.py (bcrypt, PyJWT)
├── api/               # deps.py (get_db, get_current_user) · v1/ (router, auth, documents, query)
├── models/            # SQLAlchemy models: user, document, conversation, message
├── schemas/           # Pydantic: auth, document, query
├── services/          # pdf_processor, embedding_service, vector_store, llm_service
└── db/                # base.py (model registry) · session.py (engine + FK pragma)
alembic/               # versioned migrations — never create_all in production
tests/                 # pytest: auth + document isolation (TestClient, temp DB)
```

## Quality gates

```bash
ruff check app tests     # lint
pytest -q                # 18 tests: auth, isolation, upload validation
```

## Storage layout

Everything lives under `backend/data/` — delete that folder to reset all state:

- `data/rag.db` — SQLite (users, documents, conversations, messages)
- `data/pdfs/` — uploaded PDF files
- `data/chroma/` — ChromaDB vector index (one collection per document)

## Known gaps (deliberate scope cuts)

No refresh tokens, no email verification, no rate limiting, no Docker/CI, no
Prometheus metrics. Tokens live in `localStorage` (fine for a local tool; use
httpOnly cookies behind a same-origin deployment for hardened setups). These
are documented, not hidden.

## Quick test

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" -d '{"email":"a@b.com","password":"password123"}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")

curl -F "file=@/path/to/some.pdf" -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/upload
curl -X POST http://localhost:8000/api/v1/query -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"doc_id": "<doc_id>", "question": "What is this document about?"}'
```