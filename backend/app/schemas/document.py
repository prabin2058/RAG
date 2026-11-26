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
    progress: int = 0
    error: str | None = None
    warning: str | None = None


class DocumentListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    status: str
    num_pages: int
    uploaded_at: datetime
    warning: str | None = None
