"""ChromaDB persistent client wrapper."""

import chromadb

from app.core.config import settings

_client = None


def _get_client() -> chromadb.ClientAPI:
    """Create the persistent Chroma client once and reuse it."""
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=str(settings.chroma_dir))
    return _client


def add_chunks(doc_id: str, chunks: list[dict], embeddings: list[list[float]]) -> None:
    """Store chunk texts, embeddings, and metadata in the doc's collection."""
    collection = _get_client().get_or_create_collection(
        name=doc_id, metadata={"hnsw:space": "cosine"}
    )
    collection.add(
        ids=[f"{doc_id}-{c['chunk_index']}" for c in chunks],
        embeddings=embeddings,
        documents=[c["text"] for c in chunks],
        metadatas=[
            {
                "document_id": doc_id,
                "page_number": c["page_number"],
                "chunk_index": c["chunk_index"],
            }
            for c in chunks
        ],
    )


def query_chunks(
    doc_id: str,
    embedding: list[float],
    k: int = 5,
    page_start: int | None = None,
    page_end: int | None = None,
) -> list[dict]:
    """Return the top-k most similar chunks with optional page range filter."""
    collection = _get_client().get_or_create_collection(name=doc_id)

    where_filter = None
    if page_start is not None and page_end is not None:
        where_filter = {
            "$and": [
                {"page_number": {"$gte": page_start}},
                {"page_number": {"$lte": page_end}},
            ]
        }
    elif page_start is not None:
        where_filter = {"page_number": {"$gte": page_start}}
    elif page_end is not None:
        where_filter = {"page_number": {"$lte": page_end}}

    results = collection.query(
        query_embeddings=[embedding],
        n_results=min(k, collection.count()),
        include=["documents", "metadatas", "distances"],
        where=where_filter,
    )
    chunks = []
    if not results["documents"]:
        return chunks
    for text, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
        strict=False,
    ):
        chunks.append(
            {
                "page_number": int(meta.get("page_number", 0)),
                "snippet": text[:500],  # keep snippets short for the prompt
                "distance": float(dist),
            }
        )
    return chunks


def delete_collection(doc_id: str) -> None:
    """Drop a document's collection (no-op if it doesn't exist)."""
    client = _get_client()
    try:
        client.delete_collection(name=doc_id)
    except Exception:
        pass
