"""Query and conversation endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import models
import schemas
from database import get_db
from services import embedding_service, llm_service, vector_store
from services.llm_service import OllamaUnavailableError

router = APIRouter()

PROMPT_TEMPLATE = """You are a helpful assistant that answers questions using only the context provided below,
extracted from a PDF document.

Context:
{retrieved_chunks_with_page_numbers}

Previous conversation:
{last_3_turns}

Question: {question}

Instructions:
- Answer only using the context above.
- If the answer is not present in the context, say "I couldn't find this information in the document."
- Cite the page number(s) you used in the format [Page X].
- Be concise and accurate.

Answer:"""


def _format_context(chunks: list[dict]) -> str:
    """Render retrieved chunks with page numbers for the prompt."""
    return "\n\n".join(
        f"[Page {c['page_number']}]\n{c['snippet']}" for c in chunks
    )


def _last_turns(db: Session, conversation_id: str, n: int = 3) -> str:
    """Pull the last n messages for the conversation, oldest first."""
    msgs = (
        db.query(models.Message)
        .filter(models.Message.conversation_id == conversation_id)
        .order_by(models.Message.created_at.asc(), models.Message.id.asc())
        .all()
    )
    return "\n".join(f"{m.role}: {m.content}" for m in msgs[-n:])


@router.post("/query", response_model=schemas.QueryResponse)
def query_document(req: schemas.QueryRequest, db: Session = Depends(get_db)):
    """Answer a question about a document using RAG."""
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    doc = db.get(models.Document, req.doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    if doc.status != "ready":
        raise HTTPException(
            status_code=409,
            detail=f"Document is not ready yet (status: {doc.status}).",
        )

    # Find or create the conversation
    conversation_id = req.conversation_id
    if conversation_id:
        conversation = db.get(models.Conversation, conversation_id)
        if not conversation or conversation.doc_id != req.doc_id:
            raise HTTPException(status_code=404, detail="Conversation not found for this document.")
    else:
        conversation = models.Conversation(id=str(uuid.uuid4()), doc_id=req.doc_id)
        db.add(conversation)
        db.commit()
        conversation_id = conversation.id

    # Retrieve relevant chunks
    question_embedding = embedding_service.embed_texts([req.question])[0]
    chunks = vector_store.query_chunks(req.doc_id, question_embedding, k=5)

    if not chunks:
        answer = "I couldn't find this information in the document."
    else:
        prompt = PROMPT_TEMPLATE.format(
            retrieved_chunks_with_page_numbers=_format_context(chunks),
            last_3_turns=_last_turns(db, conversation_id),
            question=req.question,
        )
        try:
            answer = llm_service.generate_answer(prompt)
        except OllamaUnavailableError as e:
            raise HTTPException(status_code=503, detail=str(e)) from e

    # Persist the exchange
    db.add(models.Message(conversation_id=conversation_id, role="user", content=req.question))
    db.add(models.Message(conversation_id=conversation_id, role="assistant", content=answer))
    db.commit()

    sources = [
        schemas.Source(page_number=c["page_number"], snippet=c["snippet"]) for c in chunks
    ]
    return schemas.QueryResponse(answer=answer, sources=sources, conversation_id=conversation_id)


@router.get("/conversations/{doc_id}", response_model=schemas.ConversationsResponse)
def get_conversations(doc_id: str, db: Session = Depends(get_db)):
    """Return full chat history for a document, grouped by conversation."""
    doc = db.get(models.Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    conversations = (
        db.query(models.Conversation)
        .filter(models.Conversation.doc_id == doc_id)
        .order_by(models.Conversation.created_at.asc())
        .all()
    )
    result = []
    for conv in conversations:
        messages = [
            schemas.MessageOut(role=m.role, content=m.content, created_at=m.created_at)
            for m in sorted(conv.messages, key=lambda m: (m.created_at, m.id))
        ]
        result.append(
            schemas.ConversationOut(id=conv.id, created_at=conv.created_at, messages=messages)
        )
    return schemas.ConversationsResponse(doc_id=doc_id, conversations=result)