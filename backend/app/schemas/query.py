"""Query and conversation schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class QueryRequest(BaseModel):
    doc_id: str
    question: str
    conversation_id: str | None = None
    page_start: int | None = None  # filter: search from this page
    page_end: int | None = None    # filter: search up to this page


class Source(BaseModel):
    page_number: int
    snippet: str


class QueryResponse(BaseModel):
    answer: str
    sources: list[Source]
    conversation_id: str


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role: str
    content: str
    created_at: datetime


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    messages: list[MessageOut]


class ConversationsResponse(BaseModel):
    doc_id: str
    conversations: list[ConversationOut]
