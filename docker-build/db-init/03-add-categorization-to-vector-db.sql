-- Add categorization support to vector_db document_chunks table
-- This script adds category and tag support to the existing document_chunks table
-- Run this manually: PGPASSWORD=password psql -h localhost -U postgres -d vector_db -f 03-add-categorization-to-vector-db.sql
--
-- IMPORTANT: This script now uses vectors.document_chunks (not public.document_chunks)
-- to match the application code expectations

\c vector_db;

-- Add categorization columns to existing document_chunks table (vectors schema)
ALTER TABLE vectors.document_chunks
ADD COLUMN IF NOT EXISTS category_ids VARCHAR(36)[] DEFAULT '{}' NOT NULL;

ALTER TABLE vectors.document_chunks
ADD COLUMN IF NOT EXISTS tag_ids VARCHAR(36)[] DEFAULT '{}' NOT NULL;

ALTER TABLE vectors.document_chunks
ADD COLUMN IF NOT EXISTS content_type VARCHAR(50);

-- Create GIN indexes for fast array-based filtering
CREATE INDEX IF NOT EXISTS idx_document_chunks_category_ids
ON vectors.document_chunks USING gin (category_ids);

CREATE INDEX IF NOT EXISTS idx_document_chunks_tag_ids
ON vectors.document_chunks USING gin (tag_ids);

-- Create index on content_type for filtering
CREATE INDEX IF NOT EXISTS idx_document_chunks_content_type
ON vectors.document_chunks (content_type);

-- Create composite indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_document_chunks_tenant_categories
ON vectors.document_chunks (tenant_id) WHERE array_length(category_ids, 1) > 0;

CREATE INDEX IF NOT EXISTS idx_document_chunks_tenant_tags
ON vectors.document_chunks (tenant_id) WHERE array_length(tag_ids, 1) > 0;

-- Grant permissions
GRANT ALL ON TABLE vectors.document_chunks TO postgres;

-- Show the updated table structure
\d vectors.document_chunks

-- Show confirmation
SELECT 'Categorization columns successfully added to vector_db.vectors.document_chunks' as status;