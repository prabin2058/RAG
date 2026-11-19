"""Cross-encoder reranker — re-scores retrieved chunks for higher relevance."""

from sentence_transformers import CrossEncoder

_model = None

# Small, fast cross-encoder (~80MB) optimized for reranking
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def _get_model() -> CrossEncoder:
    global _model
    if _model is None:
        _model = CrossEncoder(RERANKER_MODEL, max_length=512)
    return _model


def rerank_chunks(
    query: str, chunks: list[dict], top_n: int = 3
) -> list[dict]:
    """Re-score chunks using a cross-encoder and return the top_n most relevant.

    Each chunk dict must have a 'snippet' key with the text content.
    Returns chunks sorted by cross-encoder score (descending), with 'rerank_score' added.
    """
    if not chunks:
        return []

    model = _get_model()

    # Build query-document pairs for the cross-encoder
    pairs = [(query, c["snippet"]) for c in chunks]

    # Get cross-encoder scores
    scores = model.predict(pairs)

    # Attach scores to chunks and sort
    for chunk, score in zip(chunks, scores, strict=False):
        chunk["rerank_score"] = float(score)

    reranked = sorted(chunks, key=lambda c: c["rerank_score"], reverse=True)
    return reranked[:top_n]
