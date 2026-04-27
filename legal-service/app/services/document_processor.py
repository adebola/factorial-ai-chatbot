"""Document processing pipeline: download from MinIO, extract text, chunk, embed, store.

Legal documents use larger chunks than the RAG pipeline (1500 chars / 300
overlap vs 1000/200) because legal clauses are longer contextual units — a
termination clause or indemnity provision split mid-sentence loses its meaning.
"""
import os
import io
import hashlib
import logging
import tempfile
from datetime import datetime, timezone

from ..core.config import settings
from ..core.database import SessionLocal
from ..models.document import Document

logger = logging.getLogger(__name__)


async def process_document(document_id: str) -> None:
    """Main entry point for background document processing.

    1. Load the Document row
    2. Download the file from MinIO
    3. Extract text (PDF / DOCX / TXT)
    4. Split into chunks
    5. Embed + store in pgvector
    6. Update processing_status
    """
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            logger.error(f"Document {document_id} not found")
            return

        doc.processing_status = "processing"
        db.commit()

        # Download from MinIO
        file_bytes = _download_from_minio(doc.minio_path)

        # Extract text
        pages = _extract_text(file_bytes, doc.file_type, doc.original_filename)
        doc.page_count = len(pages)

        # Flatten pages into a single text for chunking, preserving page info
        chunks = _split_into_chunks(pages)
        doc.chunk_count = len(chunks)

        if not chunks:
            doc.processing_status = "failed"
            doc.processing_error = "No text could be extracted from the document"
            doc.processed_at = datetime.now(timezone.utc)
            db.commit()
            return

        # Embed and store
        from .vector_service import ingest_chunks
        await ingest_chunks(
            tenant_id=doc.tenant_id,
            document_id=doc.id,
            chunks=chunks,
            source_type="legal_contract",
        )

        doc.processing_status = "completed"
        doc.processed_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(
            f"Document '{doc.original_filename}' processed: "
            f"{doc.page_count} pages, {doc.chunk_count} chunks"
        )

    except Exception as e:
        logger.error(f"Document processing failed for {document_id}: {e}")
        try:
            doc = db.query(Document).filter(Document.id == document_id).first()
            if doc:
                doc.processing_status = "failed"
                doc.processing_error = str(e)[:1000]
                doc.processed_at = datetime.now(timezone.utc)
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


def _download_from_minio(minio_path: str) -> bytes:
    from minio import Minio
    client = Minio(
        os.environ.get("MINIO_ENDPOINT", "localhost:9000"),
        access_key=os.environ.get("MINIO_ACCESS_KEY", "minioadmin"),
        secret_key=os.environ.get("MINIO_SECRET_KEY", "minioadmin"),
        secure=os.environ.get("MINIO_SECURE", "false").lower() == "true",
    )
    bucket = os.environ.get("MINIO_BUCKET_NAME", "chatcraft-files")
    response = client.get_object(bucket, minio_path)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def _extract_text(file_bytes: bytes, file_type: str, filename: str) -> list:
    """Extract text from a file. Returns a list of (page_number, text) tuples."""
    if file_type == "pdf":
        return _extract_pdf(file_bytes)
    elif file_type in ("docx", "doc"):
        return _extract_docx(file_bytes)
    elif file_type == "txt":
        text = file_bytes.decode("utf-8", errors="replace")
        return [(1, text)]
    else:
        raise ValueError(f"Unsupported file type: {file_type}")


def _extract_pdf(file_bytes: bytes) -> list:
    """Extract text from PDF. Returns [(page_num, text), ...]."""
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(file_bytes))
    pages = []
    for i, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append((i, text))
    return pages


def _extract_docx(file_bytes: bytes) -> list:
    """Extract text from DOCX."""
    import docx2txt
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=True) as tmp:
        tmp.write(file_bytes)
        tmp.flush()
        text = docx2txt.process(tmp.name)
    if text and text.strip():
        return [(1, text)]
    return []


def _split_into_chunks(pages: list) -> list:
    """Split extracted pages into overlapping chunks for embedding.

    Returns a list of dicts: [{content, page_number, chunk_index}, ...]
    """
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    chunks = []
    chunk_index = 0
    for page_num, text in pages:
        page_chunks = splitter.split_text(text)
        for chunk_text in page_chunks:
            chunks.append({
                "content": chunk_text,
                "page_number": page_num,
                "chunk_index": chunk_index,
            })
            chunk_index += 1

    return chunks
