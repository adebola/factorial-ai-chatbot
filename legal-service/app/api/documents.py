"""Document upload, listing, and management API."""
import os
import hashlib
import logging
from typing import List
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.database import get_db
from ..models.document import Document
from ..schemas.document import DocumentResponse, DocumentListResponse
from ..services.dependencies import TokenClaims, validate_token

logger = logging.getLogger(__name__)
router = APIRouter()

ALLOWED_EXTENSIONS = {"pdf", "docx", "doc", "txt"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


def _get_minio_client():
    from minio import Minio
    return Minio(
        os.environ.get("MINIO_ENDPOINT", "localhost:9000"),
        access_key=os.environ.get("MINIO_ACCESS_KEY", "minioadmin"),
        secret_key=os.environ.get("MINIO_SECRET_KEY", "minioadmin"),
        secure=os.environ.get("MINIO_SECURE", "false").lower() == "true",
    )


@router.post("/documents/upload", response_model=DocumentResponse, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db),
):
    """Upload a document. Processing (text extraction + vector embedding) runs in the background."""
    # Validate file extension
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # Read file
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"File exceeds {MAX_FILE_SIZE // (1024*1024)} MB limit")

    content_hash = hashlib.sha256(content).hexdigest()

    # Upload to MinIO
    bucket = os.environ.get("MINIO_BUCKET_NAME", "chatcraft-files")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    minio_path = f"tenant_{claims.tenant_id}/{settings.MINIO_LEGAL_PREFIX}/{timestamp}_{file.filename}"

    try:
        import io
        client = _get_minio_client()
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
        client.put_object(
            bucket,
            minio_path,
            io.BytesIO(content),
            length=len(content),
            content_type=file.content_type or "application/octet-stream",
        )
    except Exception as e:
        logger.error(f"MinIO upload failed: {e}")
        raise HTTPException(status_code=500, detail="File storage error")

    # Create DB record
    doc = Document(
        tenant_id=claims.tenant_id,
        original_filename=file.filename,
        file_type=ext,
        minio_path=minio_path,
        file_size_bytes=len(content),
        content_hash=content_hash,
        uploaded_by=claims.user_id,
        uploaded_by_email=claims.email,
        processing_status="pending",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # Trigger async processing
    background_tasks.add_task(_process_document_background, doc.id)

    logger.info(
        f"Document '{file.filename}' uploaded by {claims.email}, "
        f"doc_id={doc.id}, size={len(content)} bytes"
    )
    return DocumentResponse.model_validate(doc)


async def _process_document_background(document_id: str):
    """Background task that processes a document (extract text, chunk, embed)."""
    from ..services.document_processor import process_document
    try:
        await process_document(document_id)
    except Exception as e:
        logger.error(f"Background document processing failed for {document_id}: {e}")


@router.get("/documents", response_model=List[DocumentListResponse])
async def list_documents(
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db),
):
    docs = (
        db.query(Document)
        .filter(
            Document.tenant_id == claims.tenant_id,
            Document.is_deleted == False,
        )
        .order_by(Document.uploaded_at.desc())
        .all()
    )
    return [DocumentListResponse.model_validate(d) for d in docs]


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(
        Document.id == document_id,
        Document.tenant_id == claims.tenant_id,
        Document.is_deleted == False,
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentResponse.model_validate(doc)


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(
    document_id: str,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(
        Document.id == document_id,
        Document.tenant_id == claims.tenant_id,
        Document.is_deleted == False,
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    doc.is_deleted = True
    db.commit()
    logger.info(f"Document '{doc.original_filename}' soft-deleted by {claims.email}")
