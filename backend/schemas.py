"""Pydantic request/response schemas."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class UploadResponse(BaseModel):
    doc_id: str
    filename: str
    status: str


class DocumentStatus(BaseModel):
    doc_id: str
    status: str
    num_pages: int
    error: Optional[str] = None


class DocumentListItem(BaseModel):
    id: str
    filename: str
    status: str
    num_pages: int
    uploaded_at: datetime


class QueryRequest(BaseModel):
    doc_id: str
    question: str
    conversation_id: Optional[str] = None


class Source(BaseModel):
    page_number: int
    snippet: str


class QueryResponse(BaseModel):
    answer: str
    sources: List[Source]
    conversation_id: str


class MessageOut(BaseModel):
    role: str
    content: str
    created_at: datetime


class ConversationOut(BaseModel):
    id: str
    created_at: datetime
    messages: List[MessageOut]


class ConversationsResponse(BaseModel):
    doc_id: str
    conversations: List[ConversationOut]