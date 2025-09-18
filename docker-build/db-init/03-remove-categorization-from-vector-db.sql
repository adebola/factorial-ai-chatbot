-- Remove categorization support from vector_db document_chunks table
-- This script removes the categorization columns if needed for rollback
-- Run this manually: PGPASSWORD=password psql -h localhost -U postgres -d vector_db -f 03-remove-categorization-from-vector-db.sql

\c vector_db;

-- Drop indexes first
DROP INDEX IF EXISTS idx_document_chunks_tenant_tags;
DROP INDEX IF EXISTS idx_document_chunks_tenant_categories;
DROP INDEX IF EXISTS idx_document_chunks_content_type;
DROP INDEX IF EXISTS idx_document_chunks_tag_ids;
DROP INDEX IF EXISTS idx_document_chunks_category_ids;

-- Remove categorization columns from document_chunks table (public schema)
ALTER TABLE public.document_chunks DROP COLUMN IF EXISTS category_ids;
ALTER TABLE public.document_chunks DROP COLUMN IF EXISTS tag_ids;
ALTER TABLE public.document_chunks DROP COLUMN IF EXISTS content_type;

-- Show the updated table structure
\d public.document_chunks

-- Show confirmation
SELECT 'Categorization columns successfully removed from vector_db.public.document_chunks' as status;