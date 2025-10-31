-- =====================================================
-- RDS MIGRATION SCRIPT: Vector Database Schema
-- =====================================================
-- Database: vector_db
-- Purpose: Create vector database schema for document embeddings
-- Dependencies: 01-initialization/001-create-databases-and-extensions.sql
-- =====================================================

\c vector_db

-- =====================================================
-- CREATE SCHEMA
-- =====================================================

CREATE SCHEMA IF NOT EXISTS vectors;

-- =====================================================
-- CREATE TABLES
-- =====================================================

-- Document Chunks Table (Stores text chunks with embeddings)
CREATE TABLE IF NOT EXISTS vectors.document_chunks (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    tenant_id VARCHAR(36) NOT NULL,
    document_id VARCHAR(36),
    ingestion_id VARCHAR(36),
    content TEXT NOT NULL,
    content_hash VARCHAR(64),
    chunk_index INTEGER,
    embedding vector(1536),
    source_type VARCHAR(50),
    source_name VARCHAR(255),
    page_number INTEGER,
    section_title VARCHAR(500),
    category_ids VARCHAR(36)[],
    tag_ids VARCHAR(36)[],
    content_type VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Vector Search Indexes Table (Per-tenant index metadata)
CREATE TABLE IF NOT EXISTS vectors.vector_search_indexes (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    tenant_id VARCHAR(36) NOT NULL UNIQUE,
    total_chunks INTEGER DEFAULT 0,
    last_indexed_at TIMESTAMPTZ,
    index_version VARCHAR(20),
    avg_query_time_ms INTEGER,
    last_optimized_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =====================================================
-- CREATE INDEXES
-- =====================================================

-- Tenant-based indexes
CREATE INDEX IF NOT EXISTS idx_chunks_tenant_id
    ON vectors.document_chunks(tenant_id);

CREATE INDEX IF NOT EXISTS idx_chunks_tenant_doc
    ON vectors.document_chunks(tenant_id, document_id);

CREATE INDEX IF NOT EXISTS idx_chunks_tenant_ingestion
    ON vectors.document_chunks(tenant_id, ingestion_id);

-- Content hash for deduplication
CREATE INDEX IF NOT EXISTS idx_chunks_content_hash
    ON vectors.document_chunks(content_hash);

-- Timestamp for cleanup/maintenance
CREATE INDEX IF NOT EXISTS idx_chunks_created_at
    ON vectors.document_chunks(created_at);

-- Array indexes for category and tag filtering (GIN)
CREATE INDEX IF NOT EXISTS idx_chunks_category_ids
    ON vectors.document_chunks USING GIN(category_ids);

CREATE INDEX IF NOT EXISTS idx_chunks_tag_ids
    ON vectors.document_chunks USING GIN(tag_ids);

-- Vector similarity search index (IVFFlat with cosine distance)
-- IMPORTANT: This index dramatically improves vector search performance
-- Lists parameter (100) is optimal for datasets up to 1M vectors
-- Adjust based on your dataset size:
--   - 100 lists for < 100K vectors
--   - 1000 lists for 100K-1M vectors
--   - 10000 lists for > 1M vectors
CREATE INDEX IF NOT EXISTS idx_chunks_tenant_embedding
    ON vectors.document_chunks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Search indexes table
CREATE INDEX IF NOT EXISTS idx_search_indexes_tenant
    ON vectors.vector_search_indexes(tenant_id);

-- =====================================================
-- CREATE UPDATE TRIGGER
-- =====================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION vectors.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for document_chunks
CREATE TRIGGER update_document_chunks_updated_at
    BEFORE UPDATE ON vectors.document_chunks
    FOR EACH ROW
    EXECUTE FUNCTION vectors.update_updated_at_column();

-- Trigger for vector_search_indexes
CREATE TRIGGER update_vector_search_indexes_updated_at
    BEFORE UPDATE ON vectors.vector_search_indexes
    FOR EACH ROW
    EXECUTE FUNCTION vectors.update_updated_at_column();

-- =====================================================
-- GRANT PERMISSIONS
-- =====================================================

-- Grant usage on schema to application user
-- Replace 'app_user' with your actual RDS application username
-- GRANT USAGE ON SCHEMA vectors TO app_user;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA vectors TO app_user;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA vectors TO app_user;

-- =====================================================
-- VERIFICATION QUERIES
-- =====================================================

-- Verify schema created
SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'vectors';

-- Verify tables created
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'vectors'
ORDER BY table_name;

-- Verify indexes created
SELECT indexname FROM pg_indexes
WHERE schemaname = 'vectors'
ORDER BY indexname;

-- Verify vector extension and dimension
SELECT
    column_name,
    data_type,
    udt_name
FROM information_schema.columns
WHERE table_schema = 'vectors'
  AND table_name = 'document_chunks'
  AND column_name = 'embedding';

-- Test vector dimension (should return 1536)
SELECT vector_dims(embedding) as dimensions
FROM vectors.document_chunks
LIMIT 1;

-- =====================================================
-- SAMPLE DATA QUERY (for testing after data migration)
-- =====================================================

/*
-- Insert sample chunk (for testing only)
INSERT INTO vectors.document_chunks (
    tenant_id,
    document_id,
    content,
    content_hash,
    chunk_index,
    embedding,
    source_type,
    source_name
) VALUES (
    'test-tenant-123',
    'test-doc-456',
    'This is a sample text chunk for testing vector search.',
    encode(sha256('This is a sample text chunk for testing vector search.'::bytea), 'hex'),
    0,
    array_fill(0.0::real, ARRAY[1536])::vector,
    'document',
    'test.pdf'
);

-- Test vector similarity search
SELECT
    id,
    tenant_id,
    content,
    source_name,
    1 - (embedding <=> query_vector) as similarity
FROM vectors.document_chunks
CROSS JOIN (SELECT array_fill(0.0::real, ARRAY[1536])::vector as query_vector) q
WHERE tenant_id = 'test-tenant-123'
ORDER BY embedding <=> query_vector
LIMIT 5;
*/

-- =====================================================
-- PERFORMANCE NOTES
-- =====================================================

/*
1. IVFFlat Index Building:
   - The IVFFlat index creation may take 10-30 minutes for large datasets
   - Index is built asynchronously - queries work during building but slower
   - Run VACUUM ANALYZE after bulk inserts to update statistics

2. Query Performance:
   - Vector similarity searches with index: 10-50ms for millions of vectors
   - Without index: 1-10 seconds for same dataset
   - Increase lists parameter for larger datasets
   - Decrease lists parameter if index build takes too long

3. Storage Considerations:
   - Each 1536-dim vector: ~6KB storage
   - IVFFlat index: ~1.5x raw data size
   - 1M chunks ≈ 6GB data + 9GB index = 15GB total
   - Plan for 3x raw data size with indexes and overhead

4. Maintenance:
   - Run VACUUM ANALYZE weekly on document_chunks
   - Monitor index bloat: SELECT * FROM pg_stat_user_indexes WHERE schemaname = 'vectors'
   - Rebuild IVFFlat index if query performance degrades:
     REINDEX INDEX CONCURRENTLY idx_chunks_tenant_embedding;

5. Scaling Recommendations:
   - Partition document_chunks by tenant_id for 100+ tenants
   - Use connection pooling (PgBouncer/RDS Proxy)
   - Enable parallel query execution for large scans
   - Consider read replicas for analytics workloads
*/