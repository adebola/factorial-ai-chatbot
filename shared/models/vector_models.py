import uuid
from sqlalchemy import Column, String, Text, DateTime, Integer, ForeignKey, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

Base = declarative_base()


class DocumentChunk(Base):
    """Store text chunks from documents with embeddings"""
    __tablename__ = "document_chunks"
    __table_args__ = {"schema": "vectors"}
    
    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), nullable=False, index=True)
    document_id = Column(String(36), nullable=True, index=True)  # Reference to onboarding.documents
    ingestion_id = Column(String(36), nullable=True, index=True)  # Reference to website ingestions
    
    # Text content and metadata
    content = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False, index=True)  # For deduplication
    chunk_index = Column(Integer, nullable=False, default=0)  # Order within document
    
    # Vector embedding (1536 dimensions for OpenAI text-embedding-ada-002)
    embedding = Column(Vector(1536), nullable=False)
    
    # Metadata as JSON-like fields (for better querying)
    source_type = Column(String(50), nullable=True)  # 'document', 'website', etc.
    source_name = Column(String(255), nullable=True)  # filename or URL
    page_number = Column(Integer, nullable=True)  # for PDFs
    section_title = Column(String(500), nullable=True)  # for structured docs
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# Create indexes for better performance
Index(
    "idx_chunks_tenant_embedding",
    DocumentChunk.tenant_id,
    DocumentChunk.embedding,
    postgresql_using="ivfflat",
    postgresql_ops={"embedding": "vector_cosine_ops"}
)

Index("idx_chunks_tenant_doc", DocumentChunk.tenant_id, DocumentChunk.document_id)
Index("idx_chunks_tenant_ingestion", DocumentChunk.tenant_id, DocumentChunk.ingestion_id)
Index("idx_chunks_content_hash", DocumentChunk.content_hash)


class VectorSearchIndex(Base):
    """Metadata and statistics for vector search optimization"""
    __tablename__ = "vector_search_indexes"
    __table_args__ = {"schema": "vectors"}
    
    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), nullable=False, unique=True, index=True)
    
    # Index statistics
    total_chunks = Column(Integer, default=0)
    last_indexed_at = Column(DateTime(timezone=True), nullable=True)
    index_version = Column(String(20), default="1.0")
    
    # Performance metrics
    avg_query_time_ms = Column(Integer, default=0)
    last_optimized_at = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())