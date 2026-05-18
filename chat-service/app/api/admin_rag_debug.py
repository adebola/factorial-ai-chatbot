"""
RAG Diagnostic Admin Endpoint

Lets a SYSTEM_ADMIN inspect what the chat service would retrieve from a tenant's
vector store for a given query, including which chunks would be dropped by the
distance threshold. Does NOT call the LLM.

Used to debug retrieval misses (e.g. tenant chunks present but not surfaced).
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from ..services.dependencies import require_system_admin, TokenClaims
from ..services.pg_vector_store import PgVectorStore
from ..core.logging_config import get_logger


router = APIRouter()
logger = get_logger("admin-rag-debug")


class InspectRequest(BaseModel):
    tenant_id: str = Field(..., description="Tenant ID to inspect")
    query: str = Field(..., min_length=1, description="Query text to embed and search")
    k: int = Field(10, ge=1, le=50, description="Top-K chunks to return")
    max_distance: float = Field(
        1.5, ge=0.0, le=2.0,
        description="Cosine distance threshold used to compute dropped_by_threshold"
    )


class InspectChunk(BaseModel):
    chunk_id: str
    rank: int
    distance: float
    source_type: Optional[str]
    source_name: Optional[str]
    section_title: Optional[str]
    chunk_index: Optional[int]
    content_preview: str


class InspectResponse(BaseModel):
    tenant_id: str
    query: str
    query_embedding_dim: int
    total_chunks_in_store: int
    returned: List[InspectChunk]
    dropped_by_threshold: int


_vector_store: Optional[PgVectorStore] = None


def _get_store() -> PgVectorStore:
    """Lazy-init a module-level PgVectorStore (reuses the existing connection pool)."""
    global _vector_store
    if _vector_store is None:
        _vector_store = PgVectorStore()
    return _vector_store


@router.post("/inspect", response_model=InspectResponse)
def inspect_retrieval(
    req: InspectRequest,
    claims: TokenClaims = Depends(require_system_admin),
) -> InspectResponse:
    """
    Diagnose what would be retrieved for a query against a tenant's vector store.

    Returns the top-K chunks ordered by cosine distance, ignoring the
    distance threshold for retrieval but reporting how many would have been
    dropped by it.
    """
    store = _get_store()

    try:
        embeddings = store._generate_embeddings([req.query], tenant_id=req.tenant_id)
        query_embedding = embeddings[0]
    except Exception as e:
        logger.error(f"Failed to embed query for tenant {req.tenant_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to generate query embedding: {e}",
        )

    session = store.SessionLocal()
    try:
        total_row = session.execute(
            text("SELECT COUNT(*) AS c FROM vectors.document_chunks WHERE tenant_id = :tid"),
            {"tid": req.tenant_id},
        ).fetchone()
        total_chunks = int(total_row.c) if total_row else 0

        rows = session.execute(
            text(
                """
                SELECT id, content, source_type, source_name, section_title,
                       chunk_index,
                       (embedding <=> :q) AS distance
                FROM vectors.document_chunks
                WHERE tenant_id = :tid
                ORDER BY embedding <=> :q
                LIMIT :k
                """
            ),
            {
                "tid": req.tenant_id,
                "q": str(query_embedding),
                "k": req.k,
            },
        ).fetchall()

        returned: List[InspectChunk] = []
        dropped = 0
        for rank, row in enumerate(rows, start=1):
            dist = float(row.distance)
            if dist >= req.max_distance:
                dropped += 1
            content = row.content or ""
            returned.append(
                InspectChunk(
                    chunk_id=row.id,
                    rank=rank,
                    distance=dist,
                    source_type=row.source_type,
                    source_name=row.source_name,
                    section_title=row.section_title,
                    chunk_index=row.chunk_index,
                    content_preview=content[:400],
                )
            )

        logger.info(
            "RAG inspect run",
            extra={
                "actor": claims.user_id,
                "target_tenant": req.tenant_id,
                "query_len": len(req.query),
                "k": req.k,
                "returned": len(returned),
                "dropped_by_threshold": dropped,
                "total_chunks": total_chunks,
            },
        )

        return InspectResponse(
            tenant_id=req.tenant_id,
            query=req.query,
            query_embedding_dim=len(query_embedding),
            total_chunks_in_store=total_chunks,
            returned=returned,
            dropped_by_threshold=dropped,
        )
    finally:
        session.close()
