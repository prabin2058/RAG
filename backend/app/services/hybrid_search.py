"""Hybrid search: combines BM25 keyword search with vector similarity."""

import math
import re
from collections import Counter


def _tokenize(text: str) -> list[str]:
    """Simple whitespace + lowercase tokenizer."""
    return re.findall(r'\w+', text.lower())


def _bm25_scores(
    query_tokens: list[str],
    document_tokens: list[list[str]],
    k1: float = 1.5,
    b: float = 0.75,
) -> list[float]:
    """Compute BM25 scores for each document against the query tokens."""
    n_docs = len(document_tokens)
    if n_docs == 0:
        return []

    # Document frequencies
    df: dict[str, int] = {}
    for doc_tokens in document_tokens:
        unique_terms = set(doc_tokens)
        for term in unique_terms:
            df[term] = df.get(term, 0) + 1

    # Average document length
    avg_dl = sum(len(dt) for dt in document_tokens) / n_docs

    scores = []
    for doc_tokens in document_tokens:
        doc_len = len(doc_tokens)
        term_freq = Counter(doc_tokens)
        score = 0.0

        for qt in query_tokens:
            if qt not in df:
                continue
            # IDF component
            idf = math.log((n_docs - df[qt] + 0.5) / (df[qt] + 0.5) + 1)
            # TF component with length normalization
            tf = term_freq.get(qt, 0)
            tf_norm = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * doc_len / avg_dl))
            score += idf * tf_norm

        scores.append(score)

    return scores


def hybrid_search(
    query: str,
    vector_chunks: list[dict],
    vector_weight: float = 0.7,
    bm25_weight: float = 0.3,
    top_n: int = 3,
) -> list[dict]:
    """Combine vector similarity scores with BM25 keyword scores.

    Args:
        query: The user's search query
        vector_chunks: Chunks from vector search with 'distance' field (lower = more similar)
        vector_weight: Weight for vector similarity (0-1)
        bm25_weight: Weight for BM25 keyword match (0-1)
        top_n: Number of top results to return

    Returns:
        Chunks sorted by combined score, with 'hybrid_score' added
    """
    if not vector_chunks:
        return []

    query_tokens = _tokenize(query)
    document_tokens = [_tokenize(c["snippet"]) for c in vector_chunks]

    # Get BM25 scores
    bm25_scores = _bm25_scores(query_tokens, document_tokens)

    # Normalize vector distances to 0-1 scores (lower distance = higher score)
    distances = [c.get("distance", 1.0) for c in vector_chunks]
    max_dist = max(distances) if distances else 1.0
    vector_scores = [1.0 - (d / max_dist) if max_dist > 0 else 0.0 for d in distances]

    # Normalize BM25 scores to 0-1
    max_bm25 = max(bm25_scores) if bm25_scores else 1.0
    bm25_norm = [s / max_bm25 if max_bm25 > 0 else 0.0 for s in bm25_scores]

    # Combine scores
    for chunk, v_score, b_score in zip(vector_chunks, vector_scores, bm25_norm, strict=False):
        chunk["hybrid_score"] = vector_weight * v_score + bm25_weight * b_score

    # Sort by hybrid score (descending)
    hybrid_chunks = sorted(vector_chunks, key=lambda c: c["hybrid_score"], reverse=True)
    return hybrid_chunks[:top_n]
