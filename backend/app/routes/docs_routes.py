import uuid
import shutil
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException, Depends
from app.voice.routes import admin_access

from app import config
from app.db import get_db, serialize_doc, serialize_list, persist_mock_data
from app.rag import ingest_document_task, get_vector_store

router = APIRouter(prefix="/salons", tags=["documents"], dependencies=[Depends(admin_access)])

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post("/{salon_id}/documents")
async def upload_document(
    salon_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    """Upload PDF, DOCX, TXT, or MD for RAG ingestion."""
    db = get_db()
    salon = db.salons.find_one({"_id": salon_id})
    if not salon:
        raise HTTPException(status_code=404, detail=f"Salon '{salon_id}' not found")

    file.filename = Path((file.filename or 'document').replace('\\', '/')).name
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format '{file_ext}'. Allowed formats: PDF, DOCX, TXT, MD",
        )

    # Read content & check size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File size exceeds maximum limit of 10 MB")

    doc_id = str(uuid.uuid4())
    salon_upload_dir = config.UPLOADS_DIR / salon_id
    salon_upload_dir.mkdir(parents=True, exist_ok=True)
    saved_file_path = salon_upload_dir / f"{doc_id}_{file.filename}"

    with open(saved_file_path, "wb") as f:
        f.write(content)

    doc_record = {
        "salon_id": salon_id,
        "doc_id": doc_id,
        "filename": file.filename,
        "status": "processing",
        "chunk_count": 0,
        "uploaded_at": datetime.utcnow(),
    }
    db.documents.insert_one(doc_record)
    persist_mock_data()

    # Trigger background ingestion
    background_tasks.add_task(
        ingest_document_task,
        salon_id=salon_id,
        doc_id=doc_id,
        file_path=saved_file_path,
        filename=file.filename,
    )

    return {
        "message": f"Document '{file.filename}' uploaded and queued for indexing",
        "doc_id": doc_id,
        "filename": file.filename,
        "status": "processing",
    }


@router.get("/{salon_id}/documents")
def list_documents(salon_id: str):
    """List all documents uploaded for a salon."""
    db = get_db()
    docs = list(db.documents.find({"salon_id": salon_id}).sort("uploaded_at", -1))
    return serialize_list(docs)


@router.delete("/{salon_id}/documents/{doc_id}")
def delete_document(salon_id: str, doc_id: str):
    """Delete a document, removing its chunks from Chroma and records from Mongo."""
    db = get_db()
    doc = db.documents.find_one({"salon_id": salon_id, "doc_id": doc_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # 1. Delete from Chroma
    vector_store = get_vector_store()
    vector_store.delete_by_doc_id(salon_id=salon_id, doc_id=doc_id)

    # 2. Delete file from disk if present
    filename = doc.get("filename", "")
    target_file = config.UPLOADS_DIR / salon_id / f"{doc_id}_{filename}"
    if target_file.exists():
        try:
            target_file.unlink()
        except Exception:
            pass

    # 3. Delete from Mongo
    db.documents.delete_one({"salon_id": salon_id, "doc_id": doc_id})
    persist_mock_data()

    return {"message": f"Document '{filename}' deleted successfully", "doc_id": doc_id}
