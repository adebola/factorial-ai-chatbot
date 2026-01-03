-- =============================================================================
-- Fix Vector Database Schema - Complete Setup
-- =============================================================================
-- This script ensures the vector_db has the correct schema and tables
-- Run manually on production:
-- PGPASSWORD=your_password psql -h your_host -U dbmasteruser -d vector_db -f 04-fix-vector-db-schema.sql
--
-- Purpose:
-- 1. Create vectors schema if it doesn't exist
-- 2. Create document_chunks table in vectors schema (not public!)
-- 3. Add categorization columns (category_ids, tag_ids, content_type)
-- 4. Create all necessary indexes for performance
-- 5. Create vector_search_indexes table for statistics
--
-- Safe to run multiple times (uses IF NOT EXISTS)
-- =============================================================================

\c vector_db;

\echo '========================================='
\echo 'Starting Vector Database Schema Fix'
\echo '========================================='

-- =============================================================================
-- STEP 1: Enable Extensions
-- =============================================================================
\echo ''
\echo 'Step 1: Enabling required extensions...'

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

\echo '✓ Extensions enabled'

-- =============================================================================
-- STEP 2: Create vectors schema
-- =============================================================================
\echo ''
\echo 'Step 2: Creating vectors schema...'

CREATE SCHEMA IF NOT EXISTS vectors;
GRANT ALL ON SCHEMA vectors TO dbmasteruser;

\echo '✓ vectors schema created'

-- =============================================================================
-- STEP 3: Create document_chunks table in vectors schema
-- =============================================================================
\echo ''
\echo 'Step 3: Creating document_chunks table in vectors schema...'

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

\echo '✓ document_chunks table created'

-- =============================================================================
-- STEP 4: Add categorization columns (if they don't exist)
-- =============================================================================
\echo ''
\echo 'Step 4: Adding categorization columns to vectors.document_chunks...'

-- Add category_ids column
ALTER TABLE vectors.document_chunks
ADD COLUMN IF NOT EXISTS category_ids VARCHAR(36)[] DEFAULT '{}' NOT NULL;

-- Add tag_ids column
ALTER TABLE vectors.document_chunks
ADD COLUMN IF NOT EXISTS tag_ids VARCHAR(36)[] DEFAULT '{}' NOT NULL;

-- Add content_type column
ALTER TABLE vectors.document_chunks
ADD COLUMN IF NOT EXISTS content_type VARCHAR(50);

\echo '✓ Categorization columns added'

-- =============================================================================
-- STEP 5: Create vector_search_indexes table
-- =============================================================================
\echo ''
\echo 'Step 5: Creating vector_search_indexes table...'

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

\echo '✓ vector_search_indexes table created'

-- =============================================================================
-- STEP 6: Create indexes for optimal performance
-- =============================================================================
\echo ''
\echo 'Step 6: Creating performance indexes...'

-- Vector similarity search index (ivfflat for fast approximate nearest neighbor)
CREATE INDEX IF NOT EXISTS idx_chunks_tenant_embedding
ON vectors.document_chunks USING ivfflat (embedding vector_cosine_ops)
WHERE tenant_id IS NOT NULL;

-- Standard filtering indexes
CREATE INDEX IF NOT EXISTS idx_chunks_tenant_id
ON vectors.document_chunks (tenant_id);

CREATE INDEX IF NOT EXISTS idx_chunks_tenant_doc
ON vectors.document_chunks (tenant_id, document_id);

CREATE INDEX IF NOT EXISTS idx_chunks_tenant_ingestion
ON vectors.document_chunks (tenant_id, ingestion_id);

CREATE INDEX IF NOT EXISTS idx_chunks_content_hash
ON vectors.document_chunks (content_hash);

CREATE INDEX IF NOT EXISTS idx_chunks_created_at
ON vectors.document_chunks (created_at);

-- Categorization indexes (GIN for array operations)
CREATE INDEX IF NOT EXISTS idx_chunks_category_ids
ON vectors.document_chunks USING GIN (category_ids);

CREATE INDEX IF NOT EXISTS idx_chunks_tag_ids
ON vectors.document_chunks USING GIN (tag_ids);

CREATE INDEX IF NOT EXISTS idx_chunks_content_type
ON vectors.document_chunks (content_type);

-- Composite indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_chunks_tenant_categories
ON vectors.document_chunks (tenant_id) WHERE array_length(category_ids, 1) > 0;

CREATE INDEX IF NOT EXISTS idx_chunks_tenant_tags
ON vectors.document_chunks (tenant_id) WHERE array_length(tag_ids, 1) > 0;

-- Index for vector_search_indexes
CREATE INDEX IF NOT EXISTS idx_search_indexes_tenant
ON vectors.vector_search_indexes (tenant_id);

\echo '✓ All indexes created'

-- =============================================================================
-- STEP 7: Grant permissions
-- =============================================================================
\echo ''
\echo 'Step 7: Granting permissions...'

GRANT ALL ON TABLE vectors.document_chunks TO dbmasteruser;
GRANT ALL ON TABLE vectors.vector_search_indexes TO dbmasteruser;

\echo '✓ Permissions granted'

-- =============================================================================
-- STEP 8: Verification and Status Report
-- =============================================================================
\echo ''
\echo '========================================='
\echo 'Verification and Status Report'
\echo '========================================='

-- Check schema exists
\echo ''
\echo 'Schema Status:'
SELECT
    CASE
        WHEN EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'vectors')
        THEN '✓ vectors schema EXISTS'
        ELSE '✗ ERROR: vectors schema DOES NOT EXIST'
    END as schema_status;

-- Check tables exist
\echo ''
\echo 'Table Status:'
SELECT
    CASE
        WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'vectors' AND table_name = 'document_chunks')
        THEN '✓ vectors.document_chunks table EXISTS'
        ELSE '✗ ERROR: vectors.document_chunks table DOES NOT EXIST'
    END as chunks_table_status;

SELECT
    CASE
        WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'vectors' AND table_name = 'vector_search_indexes')
        THEN '✓ vectors.vector_search_indexes table EXISTS'
        ELSE '✗ ERROR: vectors.vector_search_indexes table DOES NOT EXIST'
    END as indexes_table_status;

-- Show table structure
\echo ''
\echo 'Table Structure - vectors.document_chunks:'
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'vectors' AND table_name = 'document_chunks'
ORDER BY ordinal_position;

-- Show indexes
\echo ''
\echo 'Indexes on vectors.document_chunks:'
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'document_chunks' AND schemaname = 'vectors'
ORDER BY indexname;

-- Show record counts
\echo ''
\echo 'Record Counts:'
SELECT COUNT(*) as total_chunks FROM vectors.document_chunks;
SELECT COUNT(*) as total_search_indexes FROM vectors.vector_search_indexes;

-- Show extension versions
\echo ''
\echo 'Extension Versions:'
SELECT extname as extension, extversion as version
FROM pg_extension
WHERE extname IN ('vector', 'uuid-ossp')
ORDER BY extname;

\echo ''
\echo '========================================='
\echo '✓ Vector Database Schema Fix COMPLETED!'
\echo '========================================='
\echo ''
\echo 'Summary:'
\echo '- vectors schema created'
\echo '- vectors.document_chunks table created with all columns'
\echo '- vectors.vector_search_indexes table created'
\echo '- All indexes created for optimal performance'
\echo '- Permissions granted'
\echo ''
\echo 'Your application should now work correctly!'
\echo '========================================='
