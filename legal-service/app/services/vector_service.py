"""Vector service — pgvector ingestion and workspace-scoped similarity search.

The legal-service uses its own table (`vectors.legal_document_chunks`) separate
from the RAG pipeline's table, to guarantee that confidential legal documents
cannot leak into customer-facing chatbot responses. Different chunking params,
different metadata, and workspace-scoped search.
"""
import os
import uuid
import hashlib
import logging
from typing import List, Optional, Dict, Any

from sqlalchemy import text

from ..core.config import settings
from ..core.database import VectorSessionLocal

logger = logging.getLogger(__name__)


def _get_openai_client():
    from openai import OpenAI
    return OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


async def ingest_chunks(
    tenant_id: str,
    document_id: str,
    chunks: List[Dict[str, Any]],
    source_type: str = "legal_contract",
) -> int:
    """Embed chunks and insert into vectors.legal_document_chunks.

    Deduplicates by content_hash within the same document.
    Returns the number of new chunks inserted.
    """
    if not chunks:
        return 0

    client = _get_openai_client()
    db = VectorSessionLocal()
    inserted = 0

    try:
        # Batch embed (OpenAI supports up to 2048 inputs per call)
        batch_size = 100
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            texts = [c["content"] for c in batch]

            response = client.embeddings.create(
                model=settings.EMBEDDING_MODEL,
                input=texts,
            )

            for j, emb_data in enumerate(response.data):
                chunk = batch[j]
                content_hash = hashlib.md5(chunk["content"].encode()).hexdigest()
                embedding = emb_data.embedding

                # Dedup check
                existing = db.execute(
                    text("""
                        SELECT id FROM vectors.legal_document_chunks
                        WHERE document_id = :doc_id AND content_hash = :hash
                        LIMIT 1
                    """),
                    {"doc_id": document_id, "hash": content_hash},
                ).fetchone()

                if existing:
                    continue

                chunk_id = str(uuid.uuid4())
                db.execute(
                    text("""
                        INSERT INTO vectors.legal_document_chunks
                            (id, tenant_id, document_id, chunk_index, content,
                             embedding, page_number, content_hash, source_type, metadata)
                        VALUES
                            (:id, :tenant_id, :document_id, :chunk_index, :content,
                             :embedding, :page_number, :content_hash, :source_type, :metadata)
                    """),
                    {
                        "id": chunk_id,
                        "tenant_id": tenant_id,
                        "document_id": document_id,
                        "chunk_index": chunk.get("chunk_index", i + j),
                        "content": chunk["content"],
                        "embedding": str(embedding),
                        "page_number": chunk.get("page_number"),
                        "content_hash": content_hash,
                        "source_type": source_type,
                        "metadata": "{}",
                    },
                )
                inserted += 1

            db.commit()

        logger.info(f"Ingested {inserted} chunks for document {document_id}")
        return inserted

    except Exception as e:
        db.rollback()
        logger.error(f"Vector ingestion failed: {e}")
        raise
    finally:
        db.close()


async def search_workspace(
    tenant_id: str,
    workspace_id: str,
    query: str,
    k: int = 10,
    threshold: float = 1.5,
) -> List[Dict[str, Any]]:
    """Workspace-scoped vector similarity search.

    Joins legal_document_chunks through workspace_documents to scope results
    to only documents currently in the active workspace (removed_at IS NULL).
    Returns chunks ordered by similarity distance.
    """
    client = _get_openai_client()
    db = VectorSessionLocal()

    try:
        # Embed the query
        response = client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=[query],
        )
        query_embedding = response.data[0].embedding

        # Workspace-scoped similarity search using the legal_db's
        # workspace_documents join table. We query the vector DB but filter
        # by document IDs that are active in the workspace.
        #
        # NOTE: workspace_documents lives in legal_db, not vector_db. We pass
        # the active document IDs as a parameter list instead of a cross-DB join.
        from ..core.database import SessionLocal
        legal_db = SessionLocal()
        try:
            from ..models.workspace import WorkspaceDocument
            active_doc_ids = [
                row.document_id
                for row in legal_db.query(WorkspaceDocument.document_id).filter(
                    WorkspaceDocument.workspace_id == workspace_id,
                    WorkspaceDocument.removed_at.is_(None),
                ).all()
            ]
        finally:
            legal_db.close()

        if not active_doc_ids:
            return []

        # pgvector cosine distance search filtered to active documents
        results = db.execute(
            text("""
                SELECT
                    c.id, c.document_id, c.content, c.page_number,
                    c.section_title, c.chunk_index, c.source_type,
                    c.embedding <=> :query_embedding AS distance
                FROM vectors.legal_document_chunks c
                WHERE c.tenant_id = :tenant_id
                  AND c.document_id = ANY(:doc_ids)
                  AND c.embedding <=> :query_embedding < :threshold
                ORDER BY distance
                LIMIT :k
            """),
            {
                "tenant_id": tenant_id,
                "query_embedding": str(query_embedding),
                "doc_ids": active_doc_ids,
                "threshold": threshold,
                "k": k,
            },
        ).fetchall()

        # Resolve document filenames for attribution
        doc_names = {}
        if results:
            doc_ids_in_results = list({r.document_id for r in results})
            legal_db = SessionLocal()
            try:
                from ..models.document import Document
                docs = legal_db.query(Document.id, Document.original_filename).filter(
                    Document.id.in_(doc_ids_in_results)
                ).all()
                doc_names = {d.id: d.original_filename for d in docs}
            finally:
                legal_db.close()

        return [
            {
                "chunk_id": r.id,
                "document_id": r.document_id,
                "document_name": doc_names.get(r.document_id, "unknown"),
                "content": r.content,
                "page_number": r.page_number,
                "section_title": r.section_title,
                "distance": float(r.distance),
            }
            for r in results
        ]

    except Exception as e:
        logger.error(f"Workspace search failed: {e}")
        raise
    finally:
        db.close()


async def search_shared_corpus(
    query: str,
    corpus_category: Optional[str] = None,
    k: int = 10,
) -> List[Dict[str, Any]]:
    """Search the shared legal corpus (cross-tenant, source_type='shared_corpus').

    Available once the shared corpus is populated (separate workstream).
    """
    client = _get_openai_client()
    db = VectorSessionLocal()

    try:
        response = client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=[query],
        )
        query_embedding = response.data[0].embedding

        sql = """
            SELECT
                c.id, c.document_id, c.content, c.page_number,
                c.section_title, c.source_type, c.metadata,
                c.embedding <=> :query_embedding AS distance
            FROM vectors.legal_document_chunks c
            WHERE c.source_type = 'shared_corpus'
              AND c.embedding <=> :query_embedding < 1.5
        """
        params: dict = {"query_embedding": str(query_embedding), "k": k}

        if corpus_category:
            sql += " AND c.metadata->>'corpus_category' = :category"
            params["category"] = corpus_category

        sql += " ORDER BY distance LIMIT :k"

        results = db.execute(text(sql), params).fetchall()

        return [
            {
                "chunk_id": r.id,
                "content": r.content,
                "page_number": r.page_number,
                "section_title": r.section_title,
                "source_type": r.source_type,
                "distance": float(r.distance),
            }
            for r in results
        ]

    except Exception as e:
        logger.error(f"Shared corpus search failed: {e}")
        return []
    finally:
        db.close()


async def delete_document_chunks(document_id: str) -> int:
    """Remove all chunks for a document from the vector store."""
    db = VectorSessionLocal()
    try:
        result = db.execute(
            text("DELETE FROM vectors.legal_document_chunks WHERE document_id = :doc_id"),
            {"doc_id": document_id},
        )
        db.commit()
        deleted = result.rowcount
        logger.info(f"Deleted {deleted} chunks for document {document_id}")
        return deleted
    except Exception as e:
        db.rollback()
        logger.error(f"Chunk deletion failed: {e}")
        raise
    finally:
        db.close()
