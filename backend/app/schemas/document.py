"""Document schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UploadResponse(BaseModel):
    doc_id: str
    filename: str
    status: str


class DocumentStatus(BaseModel):
    doc_id: str
    status: str
    num_pages: int
    error: str | None = None


class DocumentListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    status: str
    num_pages: int
    uploaded_at: datetime
