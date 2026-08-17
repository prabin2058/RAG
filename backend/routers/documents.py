"""Document endpoints: upload, list, status, delete."""

import os
import shutil
import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

import models
import schemas
from database import SessionLocal, get_db
from services import embedding_service, pdf_processor, vector_store

router = APIRouter()

PDF_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "pdfs")
os.makedirs(PDF_DIR, exist_ok=True)


def _process_document(doc_id: str) -> None:
    """Background task: extract text, chunk, embed, and store in ChromaDB.

    Opens its own DB session — the request's session is closed before
    background tasks run.
    """
    db = SessionLocal()
    try:
        doc = db.get(models.Document, doc_id)
        if not doc:
            return
        pages = pdf_processor.extract_pages(doc.filepath)
        chunks = pdf_processor.chunk_pages(pages)
        if not chunks:
            raise ValueError("No text could be extracted from this PDF.")

        embeddings = embedding_service.embed_texts([c["text"] for c in chunks])
        vector_store.add_chunks(doc.id, chunks, embeddings)

        doc.num_pages = len(pages)
        doc.status = "ready"
        doc.error = None
    except Exception as e:
        doc.status = "failed"
        doc.error = str(e)
    finally:
        db.commit()
        db.close()


@router.post("/upload", response_model=schemas.UploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Accept a PDF, kick off processing in the background, return immediately."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")

    doc_id = str(uuid.uuid4())
    safe_filename = os.path.basename(file.filename)
    filepath = os.path.join(PDF_DIR, f"{doc_id}_{safe_filename}")

    with open(filepath, "wb") as out:
        shutil.copyfileobj(file.file, out)

    doc = models.Document(id=doc_id, filename=safe_filename, filepath=filepath, status="processing")
    db.add(doc)
    db.commit()

    background_tasks.add_task(_process_document, doc_id)

    return schemas.UploadResponse(doc_id=doc_id, filename=safe_filename, status="processing")


@router.get("/documents/{doc_id}/status", response_model=schemas.DocumentStatus)
def get_document_status(doc_id: str, db: Session = Depends(get_db)):
    """Poll endpoint: returns processing/ready/failed plus page count."""
    doc = db.get(models.Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    return schemas.DocumentStatus(
        doc_id=doc.id, status=doc.status, num_pages=doc.num_pages, error=doc.error
    )


@router.get("/documents", response_model=list[schemas.DocumentListItem])
def list_documents(db: Session = Depends(get_db)):
    """Return all uploaded documents, newest first."""
    docs = db.query(models.Document).order_by(models.Document.uploaded_at.desc()).all()
    return [
        schemas.DocumentListItem(
            id=d.id,
            filename=d.filename,
            status=d.status,
            num_pages=d.num_pages,
            uploaded_at=d.uploaded_at,
        )
        for d in docs
    ]


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: str, db: Session = Depends(get_db)):
    """Delete the PDF file, SQLite record, and ChromaDB collection."""
    doc = db.get(models.Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    filepath = doc.filepath
    db.delete(doc)
    db.commit()

    if os.path.exists(filepath):
        try:
            os.remove(filepath)
        except OSError:
            pass
    vector_store.delete_collection(doc_id)

    return {"deleted": doc_id}