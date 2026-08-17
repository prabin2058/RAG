"""Query and conversation endpoints — document ownership enforced throughout."""

# ruff: noqa: E501  (PROMPT_TEMPLATE is spec-mandated text)

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
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
from app.services.llm_service import OllamaUnavailableError

router = APIRouter(tags=["query"])

PROMPT_TEMPLATE = """You are a helpful assistant that answers questions using only the context provided below,  extracted from a PDF document.

Context:
{retrieved_chunks_with_page_numbers}

Previous conversation:
{last_3_turns}

Question: {question}

Instructions:
- Answer only using the context above.  - If the answer is not present in the context, say "I couldn't find this information in the document."  - Cite the page number(s) you used in the format [Page X].
- Be concise and accurate.

Answer:"""


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
    return "\n\n".join(f"[Page {c['page_number']}]\n{c['snippet']}" for c in chunks)


def _last_turns(db: Session, conversation_id: str, n: int = 3) -> str:
    msgs = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
        .all()
    )
    return "\n".join(f"{m.role}: {m.content}" for m in msgs[-n:])


@router.post("/query", response_model=QueryResponse)
def query_document(
    req: QueryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    doc = _get_owned_document(db, req.doc_id, current_user)
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

    question_embedding = embedding_service.embed_texts([req.question])[0]
    chunks = vector_store.query_chunks(doc.id, question_embedding, k=5)

    if not chunks:
        answer = "I couldn't find this information in the document."
    else:
        prompt = PROMPT_TEMPLATE.format(
            retrieved_chunks_with_page_numbers=_format_context(chunks),
            last_3_turns=_last_turns(db, conversation.id),
            question=req.question,
        )
        try:
            answer = llm_service.generate_answer(prompt)
        except OllamaUnavailableError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)
            ) from e

    db.add(Message(conversation_id=conversation.id, role="user", content=req.question))
    db.add(Message(conversation_id=conversation.id, role="assistant", content=answer))
    db.commit()

    sources = [Source(page_number=c["page_number"], snippet=c["snippet"]) for c in chunks]
    return QueryResponse(answer=answer, sources=sources, conversation_id=conversation.id)


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
