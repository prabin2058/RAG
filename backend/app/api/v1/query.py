"""Query and conversation endpoints — document ownership enforced throughout."""

# ruff: noqa: E501  (PROMPT_TEMPLATE is spec-mandated text)

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.conversation import Conversation
from app.models.document import Document
from app.models.message import Message
from app.models.user import User
from app.schemas.query import (
    ConversationOut,
    ConversationsResponse,
    MessageOut,
    QueryRequest,
    QueryResponse,
    Source,
)
from app.services import embedding_service, llm_service, vector_store
from app.services.hybrid_search import hybrid_search
from app.services.llm_service import LLMUnavailableError
from app.services.reranker import rerank_chunks

router = APIRouter(tags=["query"])

# Shorter prompt = fewer tokens = faster generation
PROMPT_TEMPLATE = """Answer using only the context below. If not found, say "I couldn't find this information in the document." Cite pages as [Page X].

Context:
{retrieved_chunks_with_page_numbers}

Chat history:
{last_3_turns}

Question: {question}

Answer:"""

NOT_FOUND_ANSWER = "I couldn't find this information in the document."


# Chunks kept after keyword scoring and passed on to the reranker. How many are
# fetched first and how many the LLM finally reads are set in backend/.env
# (RETRIEVAL_CANDIDATES, RETRIEVAL_TOP_K).
HYBRID_KEEP = 20


def _get_owned_document(db: Session, doc_id: str, user: User) -> Document:
    doc = db.query(Document).filter(Document.id == doc_id, Document.user_id == user.id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return doc


def _get_owned_conversation(db: Session, conversation_id: str, doc: Document) -> Conversation:
    conv = db.get(Conversation, conversation_id)
    if not conv or conv.doc_id != doc.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return conv


def _format_context(chunks: list[dict]) -> str:
    return "\n\n".join(f"[Page {c['page_number']}]\n{c.get('text') or c['snippet']}" for c in chunks)


def _last_turns(db: Session, conversation_id: str, n: int = 3) -> str:
    msgs = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
        .all()
    )
    return "\n".join(f"{m.role}: {m.content}" for m in msgs[-n:])


def _prepare(req: QueryRequest, db: Session, user: User) -> tuple[Document, Conversation]:
    """Validate the request and return the document and conversation to use."""
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    doc = _get_owned_document(db, req.doc_id, user)
    if doc.status != "ready":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Document is not ready yet (status: {doc.status}).",
        )

    if req.conversation_id:
        conversation = _get_owned_conversation(db, req.conversation_id, doc)
    else:
        conversation = Conversation(id=str(uuid.uuid4()), doc_id=doc.id)
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
    return doc, conversation


def _retrieve(req: QueryRequest, doc: Document) -> list[dict]:
    """Find the chunks that best answer the question.

    1. Fetch many candidates by meaning (vector search).
    2. Re-score them with keywords too (hybrid) and keep the best HYBRID_KEEP.
    3. Rerank those with the cross-encoder, which reads question and chunk
       together, and keep the best RETRIEVAL_TOP_K for the LLM.
    """
    question_embedding = embedding_service.embed_query(req.question)
    candidates = vector_store.query_chunks(
        doc.id, question_embedding, k=settings.RETRIEVAL_CANDIDATES,
        page_start=req.page_start, page_end=req.page_end,
    )
    if not candidates:
        return []
    shortlist = hybrid_search(req.question, candidates, top_n=HYBRID_KEEP)
    return rerank_chunks(req.question, shortlist, top_n=settings.RETRIEVAL_TOP_K)


def _build_prompt(db: Session, conversation: Conversation, question: str, chunks: list[dict]) -> str:
    return PROMPT_TEMPLATE.format(
        retrieved_chunks_with_page_numbers=_format_context(chunks),
        last_3_turns=_last_turns(db, conversation.id),
        question=question,
    )


def _save_turn(conversation_id: str, question: str, answer: str) -> None:
    """Store the question and answer (own session: safe inside a stream)."""
    with SessionLocal() as s:
        s.add(Message(conversation_id=conversation_id, role="user", content=question))
        s.add(Message(conversation_id=conversation_id, role="assistant", content=answer))
        s.commit()


@router.post("/query", response_model=QueryResponse)
def query_document(
    req: QueryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc, conversation = _prepare(req, db, current_user)
    chunks = _retrieve(req, doc)

    if not chunks:
        answer = NOT_FOUND_ANSWER
    else:
        try:
            answer = llm_service.generate_answer(
                _build_prompt(db, conversation, req.question, chunks)
            )
        except LLMUnavailableError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)
            ) from e

    db.add(Message(conversation_id=conversation.id, role="user", content=req.question))
    db.add(Message(conversation_id=conversation.id, role="assistant", content=answer))
    db.commit()

    sources = [Source(page_number=c["page_number"], snippet=c["snippet"]) for c in chunks]
    return QueryResponse(answer=answer, sources=sources, conversation_id=conversation.id)


@router.post("/query/stream")
def query_document_stream(
    req: QueryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Streaming version — returns newline-delimited JSON tokens.

    The last line always has ``done: true`` with ``conversation_id`` and
    ``sources``, or ``error`` if the LLM failed.
    """
    doc, conversation = _prepare(req, db, current_user)
    chunks = _retrieve(req, doc)
    conversation_id = conversation.id
    sources = [{"page_number": c["page_number"], "snippet": c["snippet"]} for c in chunks]

    def final_line(token: str = "") -> str:
        return json.dumps({
            "token": token,
            "done": True,
            "conversation_id": conversation_id,
            "sources": sources,
        }) + "\n"

    if not chunks:
        def empty_stream():
            _save_turn(conversation_id, req.question, NOT_FOUND_ANSWER)
            yield final_line(NOT_FOUND_ANSWER)

        return StreamingResponse(empty_stream(), media_type="application/x-ndjson")

    prompt = _build_prompt(db, conversation, req.question, chunks)

    def stream_tokens():
        collected = []
        try:
            for token in llm_service.generate_answer_stream(prompt):
                collected.append(token)
                yield json.dumps({"token": token, "done": False}) + "\n"
        except LLMUnavailableError as e:
            yield json.dumps({"error": str(e), "done": True}) + "\n"
            return

        _save_turn(conversation_id, req.question, "".join(collected).strip())
        yield final_line()

    return StreamingResponse(stream_tokens(), media_type="application/x-ndjson")


@router.get("/conversations/{doc_id}", response_model=ConversationsResponse)
def get_conversations(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = _get_owned_document(db, doc_id, current_user)
    conversations = (
        db.query(Conversation)
        .filter(Conversation.doc_id == doc.id)
        .order_by(Conversation.created_at.asc())
        .all()
    )
    result = []
    for conv in conversations:
        messages = [
            MessageOut.model_validate(m)
            for m in sorted(conv.messages, key=lambda m: (m.created_at, m.id))
        ]
        result.append(
            ConversationOut(id=conv.id, created_at=conv.created_at, messages=messages)
        )
    return ConversationsResponse(doc_id=doc.id, conversations=result)
