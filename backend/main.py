"""FastAPI app entrypoint."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import models
from database import Base, engine
from routers import documents, query

Base.metadata.create_all(bind=engine)

app = FastAPI(title="RAG PDF Q&A", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    # Local-only tool with no auth; allow any origin so Vite's port
    # (5173/5174/...) never causes CORS failures.
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router, tags=["documents"])
app.include_router(query.router, tags=["query"])


@app.get("/health")
def health():
    return {"status": "ok"}