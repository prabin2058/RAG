# RAG PDF Q&A — Backend

FastAPI backend for a fully local, free, open-source RAG PDF Q&A system.

**Stack:** FastAPI · sentence-transformers (`BAAI/bge-small-en-v1.5`, local CPU embeddings) · ChromaDB (persistent local vector store) · Ollama (local LLM) · SQLite (SQLAlchemy) · pdfplumber

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
pip install -r requirements.txt
```

## Run

```bash
uvicorn main:app --reload
```

Server runs at http://localhost:8000 — interactive docs at http://localhost:8000/docs.

## Configuration (env vars)

| Variable        | Default                 | Purpose                          |
|-----------------|-------------------------|----------------------------------|
| `OLLAMA_URL`    | `http://localhost:11434`| Ollama server address            |
| `OLLAMA_MODEL`  | `gemma4`                | LLM model name                   |

## API

| Method | Path                          | Description                                        |
|--------|-------------------------------|----------------------------------------------------|
| POST   | `/upload`                     | Upload a PDF (multipart). Returns `{doc_id, filename, status}` immediately; processing runs in the background. |
| GET    | `/documents/{doc_id}/status`  | Poll `processing` → `ready` / `failed`             |
| GET    | `/documents`                  | List all documents                                 |
| DELETE | `/documents/{doc_id}`         | Delete PDF file, DB record, and Chroma collection  |
| POST   | `/query`                      | Ask a question: `{doc_id, question, conversation_id?}` → `{answer, sources, conversation_id}` |
| GET    | `/conversations/{doc_id}`     | Full chat history grouped by conversation          |

## Storage layout

Everything lives under `backend/data/` — delete that folder to reset all state:

- `data/rag.db` — SQLite metadata + chat history
- `data/pdfs/` — uploaded PDF files
- `data/chroma/` — ChromaDB vector index (one collection per document)

## Quick test

```bash
curl -F "file=@/path/to/some.pdf" http://localhost:8000/upload
curl http://localhost:8000/documents/<doc_id>/status
curl -X POST http://localhost:8000/query -H "Content-Type: application/json" \
  -d '{"doc_id": "<doc_id>", "question": "What is this document about?"}'
```
