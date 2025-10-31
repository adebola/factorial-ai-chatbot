-- Development Environment Cleanup: Remove duplicate public.document_chunks
-- This script removes the duplicate document_chunks table from public schema in development
-- keeping only the vectors.document_chunks table for consistency

\c vector_db;

\echo 'Development environment cleanup: Removing duplicate public.document_chunks...'

-- Check what tables exist in both schemas
\echo 'Current table status:'
SELECT
    'vectors.document_chunks' as table_location,
    CASE
        WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'vectors' AND table_name = 'document_chunks')
        THEN 'EXISTS'
        ELSE 'MISSING'
    END as status;

SELECT
    'public.document_chunks' as table_location,
    CASE
        WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'document_chunks')
        THEN 'EXISTS'
        ELSE 'MISSING'
    END as status;

-- Show record counts if both exist
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'vectors' AND table_name = 'document_chunks') THEN
        RAISE NOTICE 'vectors.document_chunks record count: %', (SELECT COUNT(*) FROM vectors.document_chunks);
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'document_chunks') THEN
        RAISE NOTICE 'public.document_chunks record count: %', (SELECT COUNT(*) FROM public.document_chunks);
    END IF;
END $$;

-- Remove public.document_chunks if it exists
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'document_chunks') THEN

        RAISE NOTICE 'Dropping duplicate public.document_chunks table...';

        -- Drop all indexes on public.document_chunks first
        DROP INDEX IF EXISTS public.idx_document_chunks_category_ids;
        DROP INDEX IF EXISTS public.idx_document_chunks_tag_ids;
        DROP INDEX IF EXISTS public.idx_document_chunks_content_type;
        DROP INDEX IF EXISTS public.idx_document_chunks_tenant_categories;
        DROP INDEX IF EXISTS public.idx_document_chunks_tenant_tags;
        DROP INDEX IF EXISTS public.idx_chunks_tenant_embedding;
        DROP INDEX IF EXISTS public.idx_chunks_tenant_id;
        DROP INDEX IF EXISTS public.idx_chunks_tenant_doc;
        DROP INDEX IF EXISTS public.idx_chunks_tenant_ingestion;
        DROP INDEX IF EXISTS public.idx_chunks_content_hash;
        DROP INDEX IF EXISTS public.idx_chunks_created_at;

        -- Drop the table
        DROP TABLE public.document_chunks;

        RAISE NOTICE 'Successfully removed duplicate public.document_chunks table';

    ELSE
        RAISE NOTICE 'No duplicate public.document_chunks table found - cleanup not needed';
    END IF;
END $$;

-- Verify final state
\echo 'Final verification:'
SELECT
    'vectors.document_chunks' as table_location,
    CASE
        WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'vectors' AND table_name = 'document_chunks')
        THEN 'EXISTS'
        ELSE 'MISSING'
    END as status,
    CASE
        WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'vectors' AND table_name = 'document_chunks')
        THEN (SELECT COUNT(*)::text FROM vectors.document_chunks)
        ELSE '0'
    END as record_count;

SELECT
    'public.document_chunks' as table_location,
    CASE
        WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'document_chunks')
        THEN 'EXISTS (UNEXPECTED!)'
        ELSE 'REMOVED (CORRECT)'
    END as status;

\echo 'Development environment cleanup completed!'
\echo 'Now using vectors.document_chunks consistently across all services.'