-- Production Vector Database Fix Script
-- This script ensures the document_chunks table has all required categorization columns
-- Run this on your production vector_db database

-- Ensure we're working with the correct database
\echo 'Starting vector_db schema fix...'

-- Check if document_chunks table exists in public schema
SELECT
    CASE
        WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'document_chunks')
        THEN 'public.document_chunks table EXISTS'
        ELSE 'ERROR: public.document_chunks table DOES NOT EXIST'
    END as table_status;

-- Check if document_chunks table exists in vectors schema (legacy)
SELECT
    CASE
        WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'vectors' AND table_name = 'document_chunks')
        THEN 'vectors.document_chunks table EXISTS (legacy)'
        ELSE 'vectors.document_chunks table does not exist (expected)'
    END as legacy_table_status;

-- Show current column structure
\echo 'Current document_chunks table structure:'
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'document_chunks'
ORDER BY ordinal_position;

-- Add categorization columns if they don't exist
\echo 'Adding categorization columns...'

-- Add category_ids column
ALTER TABLE public.document_chunks
ADD COLUMN IF NOT EXISTS category_ids VARCHAR(36)[] DEFAULT '{}' NOT NULL;

-- Add tag_ids column
ALTER TABLE public.document_chunks
ADD COLUMN IF NOT EXISTS tag_ids VARCHAR(36)[] DEFAULT '{}' NOT NULL;

-- Add content_type column
ALTER TABLE public.document_chunks
ADD COLUMN IF NOT EXISTS content_type VARCHAR(50);

\echo 'Creating indexes for categorization columns...'

-- Create GIN indexes for array columns (for fast filtering)
CREATE INDEX IF NOT EXISTS idx_document_chunks_category_ids
ON public.document_chunks USING GIN (category_ids);

CREATE INDEX IF NOT EXISTS idx_document_chunks_tag_ids
ON public.document_chunks USING GIN (tag_ids);

-- Create regular index for content_type
CREATE INDEX IF NOT EXISTS idx_document_chunks_content_type
ON public.document_chunks (content_type);

\echo 'Verifying final table structure...'

-- Show final column structure
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'document_chunks'
ORDER BY ordinal_position;

-- Show indexes
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'document_chunks' AND schemaname = 'public'
ORDER BY indexname;

-- Show record count
SELECT COUNT(*) as total_chunks FROM public.document_chunks;

\echo 'Vector database schema fix completed!'
\echo 'The document_chunks table now has all required categorization columns.'