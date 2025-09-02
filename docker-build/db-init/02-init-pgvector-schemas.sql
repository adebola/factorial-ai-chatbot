-- Initialize pgvector schemas and tables for FactorialBot production
-- This script runs after database creation and creates the shared vector_db with proper schemas

-- Connect to vector_db and set up vector schema and tables
\c vector_db;

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create the vectors schema (as expected by shared/models/vector_models.py)
CREATE SCHEMA IF NOT EXISTS vectors;

-- Set search path to include vectors schema
ALTER DATABASE vector_db SET search_path TO public, vectors;

-- Grant permissions to postgres user on schema
GRANT ALL ON SCHEMA vectors TO postgres;

-- Show pgvector version
SELECT 'pgvector version: ' || extversion as info FROM pg_extension WHERE extname = 'vector';

-- Create document_chunks table in vectors schema (matching vector_models.py)
CREATE TABLE IF NOT EXISTS vectors.document_chunks (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    tenant_id VARCHAR(36) NOT NULL,
    document_id VARCHAR(36), -- Reference to onboarding service documents
    ingestion_id VARCHAR(36), -- Reference to website ingestions
    
    -- Text content and metadata
    content TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    chunk_index INTEGER NOT NULL DEFAULT 0,
    
    -- Vector embedding (1536 dimensions for OpenAI text-embedding-ada-002)
    embedding vector(1536) NOT NULL,
    
    -- Metadata fields
    source_type VARCHAR(50),
    source_name VARCHAR(255),
    page_number INTEGER,
    section_title VARCHAR(500),
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create vector_search_indexes table in vectors schema (matching vector_models.py)
CREATE TABLE IF NOT EXISTS vectors.vector_search_indexes (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    tenant_id VARCHAR(36) NOT NULL UNIQUE,
    
    -- Index statistics
    total_chunks INTEGER DEFAULT 0,
    last_indexed_at TIMESTAMPTZ,
    index_version VARCHAR(20) DEFAULT '1.0',
    
    -- Performance metrics
    avg_query_time_ms INTEGER DEFAULT 0,
    last_optimized_at TIMESTAMPTZ,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for optimal vector search performance
-- Primary tenant-based index for vector similarity search (matching vector_models.py)
CREATE INDEX IF NOT EXISTS idx_chunks_tenant_embedding 
ON vectors.document_chunks USING ivfflat (embedding vector_cosine_ops) 
WHERE tenant_id IS NOT NULL;

-- Standard indexes for filtering and joins (matching vector_models.py)
CREATE INDEX IF NOT EXISTS idx_chunks_tenant_id ON vectors.document_chunks (tenant_id);
CREATE INDEX IF NOT EXISTS idx_chunks_tenant_doc ON vectors.document_chunks (tenant_id, document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_tenant_ingestion ON vectors.document_chunks (tenant_id, ingestion_id);
CREATE INDEX IF NOT EXISTS idx_chunks_content_hash ON vectors.document_chunks (content_hash);
CREATE INDEX IF NOT EXISTS idx_chunks_created_at ON vectors.document_chunks (created_at);

-- Index for vector_search_indexes
CREATE INDEX IF NOT EXISTS idx_search_indexes_tenant ON vectors.vector_search_indexes (tenant_id);

-- Grant permissions to postgres user on tables
GRANT ALL ON TABLE vectors.document_chunks TO postgres;
GRANT ALL ON TABLE vectors.vector_search_indexes TO postgres;

-- Connect to chat service database and ensure pgvector is available
\c chatbot_db;
CREATE EXTENSION IF NOT EXISTS vector;

-- Connect to onboarding service database and ensure pgvector is available
\c onboard_db;
CREATE EXTENSION IF NOT EXISTS vector;

-- Final status
\c postgres;
SELECT 'pgvector schemas and vector tables initialization completed successfully!' as status;