-- Production Fix: Add categorization columns to vectors.document_chunks
-- This script updates the existing vectors.document_chunks table in production
-- to include the categorization columns that the application expects

\c vector_db;

\echo 'Checking current vectors.document_chunks table...'

-- Verify the table exists in vectors schema
SELECT
    CASE
        WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'vectors' AND table_name = 'document_chunks')
        THEN 'vectors.document_chunks EXISTS'
        ELSE 'ERROR: vectors.document_chunks DOES NOT EXIST'
    END as table_status;

-- Show current record count
SELECT COUNT(*) as current_record_count FROM vectors.document_chunks;

-- Show current columns
\echo 'Current column structure:'
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'vectors' AND table_name = 'document_chunks'
ORDER BY ordinal_position;

\echo 'Adding categorization columns to vectors.document_chunks...'

-- Add categorization columns if they don't exist
ALTER TABLE vectors.document_chunks
ADD COLUMN IF NOT EXISTS category_ids VARCHAR(36)[] DEFAULT '{}' NOT NULL;

ALTER TABLE vectors.document_chunks
ADD COLUMN IF NOT EXISTS tag_ids VARCHAR(36)[] DEFAULT '{}' NOT NULL;

ALTER TABLE vectors.document_chunks
ADD COLUMN IF NOT EXISTS content_type VARCHAR(50);

\echo 'Creating categorization indexes...'

-- Create GIN indexes for fast array-based filtering
CREATE INDEX IF NOT EXISTS idx_vectors_document_chunks_category_ids
ON vectors.document_chunks USING gin (category_ids);

CREATE INDEX IF NOT EXISTS idx_vectors_document_chunks_tag_ids
ON vectors.document_chunks USING gin (tag_ids);

-- Create index on content_type for filtering
CREATE INDEX IF NOT EXISTS idx_vectors_document_chunks_content_type
ON vectors.document_chunks (content_type);

-- Create composite indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_vectors_document_chunks_tenant_categories
ON vectors.document_chunks (tenant_id) WHERE array_length(category_ids, 1) > 0;

CREATE INDEX IF NOT EXISTS idx_vectors_document_chunks_tenant_tags
ON vectors.document_chunks (tenant_id) WHERE array_length(tag_ids, 1) > 0;

\echo 'Verifying final table structure...'

-- Show updated column structure
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'vectors' AND table_name = 'document_chunks'
ORDER BY ordinal_position;

-- Show all indexes on the table
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'document_chunks' AND schemaname = 'vectors'
ORDER BY indexname;

-- Verify record count unchanged
SELECT COUNT(*) as final_record_count FROM vectors.document_chunks;

\echo 'Production vectors schema fix completed successfully!'
\echo 'The vectors.document_chunks table now has all required categorization columns.'
\echo 'Application code has been updated to use vectors.document_chunks consistently.'