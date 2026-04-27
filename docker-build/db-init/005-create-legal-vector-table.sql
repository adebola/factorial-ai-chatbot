-- Legal document chunks — separate from the RAG pipeline's document_chunks
-- table so confidential legal documents cannot leak into customer-facing
-- chatbot responses. Uses workspace-scoped search via a join to legal_db's
-- workspace_documents table (the document_id column is the join key).

CREATE TABLE IF NOT EXISTS vectors.legal_document_chunks (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL,
    document_id VARCHAR(36) NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1536),  -- text-embedding-ada-002 dimensions
    page_number INTEGER,
    section_title VARCHAR(500),
    content_hash VARCHAR(64),
    source_type VARCHAR(50) NOT NULL DEFAULT 'legal_contract',
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Lookup indexes
CREATE INDEX IF NOT EXISTS idx_legal_chunks_tenant
    ON vectors.legal_document_chunks(tenant_id);
CREATE INDEX IF NOT EXISTS idx_legal_chunks_document
    ON vectors.legal_document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_legal_chunks_source
    ON vectors.legal_document_chunks(source_type);
CREATE INDEX IF NOT EXISTS idx_legal_chunks_hash
    ON vectors.legal_document_chunks(content_hash);

-- HNSW index for fast approximate nearest-neighbour similarity search.
-- Cosine distance (vector_cosine_ops) matches the OpenAI embedding model's
-- recommended distance metric.
CREATE INDEX IF NOT EXISTS idx_legal_chunks_embedding
    ON vectors.legal_document_chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
