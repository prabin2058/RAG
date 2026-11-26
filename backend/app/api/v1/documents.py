"""Document endpoints: upload, list, status, delete — all scoped to the current user."""

import os
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.document import Document
from app.models.user import User
from app.schemas.document import DocumentListItem, DocumentStatus, UploadResponse
from app.services import document_processor, embedding_service, vector_store

router = APIRouter(tags=["documents"])


# Chunks embedded and stored per batch: keeps memory flat and stays under
# ChromaDB's per-call limit even for very large documents.
EMBED_BATCH_SIZE = 256
# Share of the progress bar used by text extraction; the rest is embedding.
EXTRACT_SHARE = 60


def _process_document(doc_id: str) -> None:
    """Background task: extract, chunk, embed, store. Own session (request's
    session closes before background tasks run)."""
    db = SessionLocal()
    doc = None
    last_saved = -1

    def save_progress(percent: int) -> None:
        nonlocal last_saved
        percent = max(0, min(100, int(percent)))
        if percent - last_saved >= 2 or percent == 100:
            doc.progress = percent
            db.commit()
            last_saved = percent

    try:
        doc = db.get(Document, doc_id)
        if not doc:
            return
        processor = document_processor.get_processor(doc.filename)
        pages = processor.extract_pages(
            doc.filepath,
            on_progress=lambda done, total: save_progress(EXTRACT_SHARE * done / total),
        )
        chunks = document_processor.chunk_pages(
            pages,
            count_tokens=embedding_service.count_tokens,
            max_tokens=embedding_service.max_tokens(),
        )
        if not chunks:
            raise ValueError("No text could be extracted from this document.")
        save_progress(EXTRACT_SHARE)

        vector_store.delete_collection(doc.id)  # clean slate if this is a retry
        for start in range(0, len(chunks), EMBED_BATCH_SIZE):
            batch = chunks[start : start + EMBED_BATCH_SIZE]
            embeddings = embedding_service.embed_texts([c["text"] for c in batch])
            vector_store.add_chunks(doc.id, batch, embeddings)
            done = start + len(batch)
            save_progress(EXTRACT_SHARE + (100 - EXTRACT_SHARE) * done / len(chunks))

        doc.num_pages = processor.total_pages or len(pages)
        doc.warning = " ".join(processor.warnings) or None
        doc.progress = 100
        doc.status = "ready"
        doc.error = None
    except Exception as e:
        if doc is not None:
            doc.status = "failed"
            doc.error = str(e)
        vector_store.delete_collection(doc_id)  # don't leave half an index behind
    finally:
        db.commit()
        db.close()


def _get_owned_document(db: Session, doc_id: str, user: User) -> Document:
    """Fetch a document owned by the user or raise 404 (no existence leak)."""
    doc = db.query(Document).filter(Document.id == doc_id, Document.user_id == user.id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return doc


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    ext = document_processor._get_extension(file.filename)
    if ext not in document_processor.ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(document_processor.ALLOWED_EXTENSIONS))
        raise HTTPException(status_code=400, detail=f"Unsupported file format. Allowed: {allowed}")

    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    size = 0
    tmp_path = os.path.join(settings.files_dir, f"tmp-{uuid.uuid4()}")
    with open(tmp_path, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                out.close()
                os.remove(tmp_path)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File too large (max {settings.MAX_UPLOAD_MB} MB).",
                )
            out.write(chunk)

    doc_id = str(uuid.uuid4())
    safe_filename = os.path.basename(file.filename)
    filepath = os.path.join(settings.files_dir, f"{doc_id}_{safe_filename}")
    os.replace(tmp_path, filepath)

    doc = Document(
        id=doc_id,
        user_id=current_user.id,
        filename=safe_filename,
        filepath=filepath,
        status="processing",
    )
    db.add(doc)
    db.commit()

    background_tasks.add_task(_process_document, doc_id)

    return UploadResponse(doc_id=doc_id, filename=safe_filename, status="processing")


@router.get("/documents/{doc_id}/status", response_model=DocumentStatus)
def get_document_status(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = _get_owned_document(db, doc_id, current_user)
    return DocumentStatus(
        doc_id=doc.id,
        status=doc.status,
        num_pages=doc.num_pages,
        progress=doc.progress,
        error=doc.error,
        warning=doc.warning,
    )


@router.get("/documents", response_model=list[DocumentListItem])
def list_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    docs = (
        db.query(Document)
        .filter(Document.user_id == current_user.id)
        .order_by(Document.uploaded_at.desc())
        .all()
    )
    return docs


@router.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = _get_owned_document(db, doc_id, current_user)
    filepath = doc.filepath
    db.delete(doc)
    db.commit()

    if os.path.exists(filepath):
        try:
            os.remove(filepath)
        except OSError:
            pass
    vector_store.delete_collection(doc_id)
