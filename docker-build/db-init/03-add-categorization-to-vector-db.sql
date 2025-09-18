-- Add categorization support to vector_db document_chunks table
-- This script adds category and tag support to the existing document_chunks table
-- Run this manually: PGPASSWORD=password psql -h localhost -U postgres -d vector_db -f 03-add-categorization-to-vector-db.sql

\c vector_db;

-- Add categorization columns to existing document_chunks table (public schema)
ALTER TABLE public.document_chunks
ADD COLUMN IF NOT EXISTS category_ids VARCHAR(36)[] DEFAULT '{}' NOT NULL;

ALTER TABLE public.document_chunks
ADD COLUMN IF NOT EXISTS tag_ids VARCHAR(36)[] DEFAULT '{}' NOT NULL;

ALTER TABLE public.document_chunks
ADD COLUMN IF NOT EXISTS content_type VARCHAR(50);

-- Create GIN indexes for fast array-based filtering
CREATE INDEX IF NOT EXISTS idx_document_chunks_category_ids
ON public.document_chunks USING gin (category_ids);

CREATE INDEX IF NOT EXISTS idx_document_chunks_tag_ids
ON public.document_chunks USING gin (tag_ids);

-- Create index on content_type for filtering
CREATE INDEX IF NOT EXISTS idx_document_chunks_content_type
ON public.document_chunks (content_type);

-- Create composite indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_document_chunks_tenant_categories
ON public.document_chunks (tenant_id) WHERE array_length(category_ids, 1) > 0;

CREATE INDEX IF NOT EXISTS idx_document_chunks_tenant_tags
ON public.document_chunks (tenant_id) WHERE array_length(tag_ids, 1) > 0;

-- Grant permissions
GRANT ALL ON TABLE public.document_chunks TO postgres;

-- Show the updated table structure
\d public.document_chunks

-- Show confirmation
SELECT 'Categorization columns successfully added to vector_db.public.document_chunks' as status;