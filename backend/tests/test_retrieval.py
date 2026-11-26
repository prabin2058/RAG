"""Tests for chunk sizing, query embedding, retrieval order, streaming and
production settings. No ML model or LLM is loaded: those parts are faked."""

import json
import uuid

import pytest
from pydantic import ValidationError

from app.api.v1 import query as query_api
from app.core.config import DEV_SECRET_KEY, Settings
from app.models.document import Document
from app.models.message import Message
from app.services import document_processor, embedding_service
from tests.conftest import TestSession, auth_headers


def _count_words(text: str) -> int:
    return len(text.split())


# --- Chunk sizing (item 1) -----------------------------------------------------


def test_chunks_over_token_limit_are_split_without_losing_text():
    text = " ".join(f"w{i}" for i in range(240))  # one chunk by words
    chunks = document_processor.chunk_pages([(1, text)], count_tokens=_count_words, max_tokens=50)
    assert all(_count_words(c["text"]) <= 50 for c in chunks)
    assert " ".join(c["text"] for c in chunks).split() == text.split()
    assert [c["chunk_index"] for c in chunks] == list(range(len(chunks)))


def test_split_table_chunks_keep_their_title():
    rows = "\n".join(f"Name: item{i} | Value: {i}" for i in range(20))
    page = f"{document_processor.TABLE_MARKER} Table 1 on page 3. Columns: Name | Value\n{rows}"
    chunks = document_processor.chunk_pages([(3, page)], count_tokens=_count_words, max_tokens=30)
    assert len(chunks) > 1
    assert all(c["text"].startswith("Table 1 on page 3.") for c in chunks)
    assert all(_count_words(c["text"]) <= 30 for c in chunks)


def test_chunks_without_token_counter_are_unchanged():
    text = "Short page. " * 10
    assert len(document_processor.chunk_pages([(1, text)])) == 1


# --- Query prefix (item 2) -----------------------------------------------------


def test_embed_query_adds_bge_prefix(monkeypatch):
    seen = []

    def fake_embed(texts):
        seen.extend(texts)
        return [[0.0]]

    monkeypatch.setattr(embedding_service, "embed_texts", fake_embed)
    embedding_service.embed_query("What is RAG?")
    assert seen == [embedding_service.QUERY_PREFIX + "What is RAG?"]


# --- Retrieval and streaming (items 3, 4, 10) ------------------------------------


@pytest.fixture()
def ready_doc(db, user_a):
    doc = Document(
        id=str(uuid.uuid4()),
        user_id=user_a["user"]["id"],
        filename="doc.pdf",
        filepath="/nonexistent/doc.pdf",
        status="ready",
        progress=100,
    )
    db.add(doc)
    db.commit()
    return doc


@pytest.fixture()
def fake_search(monkeypatch):
    """Fake the embedding model, vector store and reranker; record what is used."""
    calls = {}
    monkeypatch.setattr(query_api.embedding_service, "embed_query", lambda q: [0.0])
    monkeypatch.setattr(query_api, "SessionLocal", TestSession)

    def fake_query_chunks(doc_id, emb, k, page_start=None, page_end=None):
        calls["k"] = k
        return calls.get("candidates", [])

    def fake_rerank(question, chunks, top_n):
        calls["rerank_in"] = len(chunks)
        calls["rerank_top_n"] = top_n
        return chunks[:top_n]

    monkeypatch.setattr(query_api.vector_store, "query_chunks", fake_query_chunks)
    monkeypatch.setattr(query_api, "rerank_chunks", fake_rerank)
    return calls


def _stream(client, token, doc_id, question="What is it?"):
    res = client.post(
        "/api/v1/query/stream",
        json={"doc_id": doc_id, "question": question},
        headers=auth_headers(token),
    )
    assert res.status_code == 200
    return [json.loads(line) for line in res.text.splitlines() if line.strip()]


def test_stream_with_no_results_returns_conversation_id(client, db, user_a, ready_doc, fake_search):
    lines = _stream(client, user_a["token"], ready_doc.id)
    last = lines[-1]
    assert last["done"] is True
    assert last["conversation_id"]
    assert last["token"] == query_api.NOT_FOUND_ANSWER
    saved = db.query(Message).filter(Message.conversation_id == last["conversation_id"]).count()
    assert saved == 2


def test_retrieval_fetches_many_and_reranks_to_top_k(
    client, user_a, ready_doc, fake_search, monkeypatch
):
    fake_search["candidates"] = [
        {"page_number": i, "text": f"chunk {i} text", "snippet": f"chunk {i}", "distance": i / 100}
        for i in range(1, 31)
    ]
    prompts = []

    def fake_stream(prompt):
        prompts.append(prompt)
        yield "Answer [Page 1]"

    monkeypatch.setattr(query_api.llm_service, "generate_answer_stream", fake_stream)

    lines = _stream(client, user_a["token"], ready_doc.id)

    from app.core.config import settings

    assert fake_search["k"] == settings.RETRIEVAL_CANDIDATES
    assert fake_search["rerank_in"] == query_api.HYBRID_KEEP
    assert fake_search["rerank_top_n"] == settings.RETRIEVAL_TOP_K
    last = lines[-1]
    assert last["conversation_id"]
    assert len(last["sources"]) == settings.RETRIEVAL_TOP_K
    assert prompts[0].count(" text\n\n[Page ") + 1 == settings.RETRIEVAL_TOP_K
    assert "chunk 1 text" in prompts[0]  # the LLM reads full text, not the snippet


# --- Production secret key (item 16) ---------------------------------------------


def _settings(**values):
    return Settings(_env_file=None, LLM_PROVIDER="ollama", **values)


def test_production_rejects_dev_secret_key():
    with pytest.raises(ValidationError, match="real SECRET_KEY"):
        _settings(ENVIRONMENT="production", SECRET_KEY=DEV_SECRET_KEY)


def test_production_rejects_short_secret_key():
    with pytest.raises(ValidationError, match="at least 32"):
        _settings(ENVIRONMENT="production", SECRET_KEY="too-short")


def test_production_accepts_strong_key_and_development_allows_default():
    assert _settings(ENVIRONMENT="production", SECRET_KEY="x" * 48).ENVIRONMENT == "production"
    assert _settings().SECRET_KEY == DEV_SECRET_KEY
