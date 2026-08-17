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
    doc_id: str, embedding: list[float], k: int = 5
) -> list[dict]:
    """Return the top-k most similar chunks: {page_number, snippet, distance}."""
    collection = _get_client().get_or_create_collection(name=doc_id)
    results = collection.query(
        query_embeddings=[embedding],
        n_results=min(k, collection.count()),
        include=["documents", "metadatas", "distances"],
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
