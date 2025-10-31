-- Production Schema Fix Script
-- This script resolves the schema mismatch between vectors.document_chunks and public.document_chunks
-- and ensures the categorization columns exist where the application expects them

\c vector_db;

\echo 'Checking current document_chunks table locations...'

-- Check if document_chunks exists in vectors schema
SELECT
    CASE
        WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'vectors' AND table_name = 'document_chunks')
        THEN 'YES'
        ELSE 'NO'
    END as vectors_table_exists;

-- Check if document_chunks exists in public schema
SELECT
    CASE
        WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'document_chunks')
        THEN 'YES'
        ELSE 'NO'
    END as public_table_exists;

-- Count records in vectors schema if it exists
SELECT
    CASE
        WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'vectors' AND table_name = 'document_chunks')
        THEN (SELECT COUNT(*)::text FROM vectors.document_chunks)
        ELSE 'Table does not exist'
    END as vectors_record_count;

-- Count records in public schema if it exists
SELECT
    CASE
        WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'document_chunks')
        THEN (SELECT COUNT(*)::text FROM public.document_chunks)
        ELSE 'Table does not exist'
    END as public_record_count;

\echo 'Implementing fix strategy...'

-- STRATEGY 1: If only vectors.document_chunks exists, move data to public schema
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'vectors' AND table_name = 'document_chunks')
       AND NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'document_chunks') THEN

        RAISE NOTICE 'Found vectors.document_chunks but no public.document_chunks. Creating public table...';

        -- Create the table in public schema with all required columns including categorization
        CREATE TABLE public.document_chunks (
            id VARCHAR(36) PRIMARY KEY,
            tenant_id VARCHAR(36) NOT NULL,
            document_id VARCHAR(36),
            ingestion_id VARCHAR(36),
            content TEXT NOT NULL,
            content_hash VARCHAR(64) NOT NULL,
            chunk_index INTEGER NOT NULL DEFAULT 0,
            embedding vector(1536) NOT NULL,
            source_type VARCHAR(50),
            source_name VARCHAR(255),
            page_number INTEGER,
            section_title VARCHAR(500),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            -- Categorization columns
            category_ids VARCHAR(36)[] DEFAULT '{}' NOT NULL,
            tag_ids VARCHAR(36)[] DEFAULT '{}' NOT NULL,
            content_type VARCHAR(50)
        );

        -- Copy data from vectors schema to public schema
        INSERT INTO public.document_chunks (
            id, tenant_id, document_id, ingestion_id, content, content_hash,
            chunk_index, embedding, source_type, source_name, page_number,
            section_title, created_at, updated_at
        )
        SELECT
            id, tenant_id, document_id, ingestion_id, content, content_hash,
            chunk_index, embedding, source_type, source_name, page_number,
            section_title, created_at, updated_at
        FROM vectors.document_chunks;

        RAISE NOTICE 'Data copied from vectors.document_chunks to public.document_chunks';

    END IF;
END $$;

-- STRATEGY 2: If public.document_chunks exists but lacks categorization columns, add them
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'document_chunks') THEN

        RAISE NOTICE 'public.document_chunks exists. Adding categorization columns if missing...';

        -- Add categorization columns if they don't exist
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'document_chunks' AND column_name = 'category_ids') THEN
            ALTER TABLE public.document_chunks ADD COLUMN category_ids VARCHAR(36)[] DEFAULT '{}' NOT NULL;
            RAISE NOTICE 'Added category_ids column';
        END IF;

        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'document_chunks' AND column_name = 'tag_ids') THEN
            ALTER TABLE public.document_chunks ADD COLUMN tag_ids VARCHAR(36)[] DEFAULT '{}' NOT NULL;
            RAISE NOTICE 'Added tag_ids column';
        END IF;

        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'document_chunks' AND column_name = 'content_type') THEN
            ALTER TABLE public.document_chunks ADD COLUMN content_type VARCHAR(50);
            RAISE NOTICE 'Added content_type column';
        END IF;

    END IF;
END $$;

-- STRATEGY 3: If neither exists, create public.document_chunks from scratch
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'document_chunks')
       AND NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'vectors' AND table_name = 'document_chunks') THEN

        RAISE NOTICE 'Neither public nor vectors document_chunks exists. Creating new public.document_chunks...';

        CREATE TABLE public.document_chunks (
            id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
            tenant_id VARCHAR(36) NOT NULL,
            document_id VARCHAR(36),
            ingestion_id VARCHAR(36),
            content TEXT NOT NULL,
            content_hash VARCHAR(64) NOT NULL,
            chunk_index INTEGER NOT NULL DEFAULT 0,
            embedding vector(1536) NOT NULL,
            source_type VARCHAR(50),
            source_name VARCHAR(255),
            page_number INTEGER,
            section_title VARCHAR(500),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            -- Categorization columns
            category_ids VARCHAR(36)[] DEFAULT '{}' NOT NULL,
            tag_ids VARCHAR(36)[] DEFAULT '{}' NOT NULL,
            content_type VARCHAR(50)
        );

        RAISE NOTICE 'Created new public.document_chunks table with categorization support';

    END IF;
END $$;

\echo 'Creating indexes for public.document_chunks...'

-- Create all necessary indexes on public.document_chunks
CREATE INDEX IF NOT EXISTS idx_chunks_tenant_embedding
ON public.document_chunks USING ivfflat (embedding vector_cosine_ops)
WHERE tenant_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_chunks_tenant_id ON public.document_chunks (tenant_id);
CREATE INDEX IF NOT EXISTS idx_chunks_tenant_doc ON public.document_chunks (tenant_id, document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_tenant_ingestion ON public.document_chunks (tenant_id, ingestion_id);
CREATE INDEX IF NOT EXISTS idx_chunks_content_hash ON public.document_chunks (content_hash);
CREATE INDEX IF NOT EXISTS idx_chunks_created_at ON public.document_chunks (created_at);

-- Categorization indexes
CREATE INDEX IF NOT EXISTS idx_document_chunks_category_ids ON public.document_chunks USING gin (category_ids);
CREATE INDEX IF NOT EXISTS idx_document_chunks_tag_ids ON public.document_chunks USING gin (tag_ids);
CREATE INDEX IF NOT EXISTS idx_document_chunks_content_type ON public.document_chunks (content_type);
CREATE INDEX IF NOT EXISTS idx_document_chunks_tenant_categories ON public.document_chunks (tenant_id) WHERE array_length(category_ids, 1) > 0;
CREATE INDEX IF NOT EXISTS idx_document_chunks_tenant_tags ON public.document_chunks (tenant_id) WHERE array_length(tag_ids, 1) > 0;

-- Grant permissions
GRANT ALL ON TABLE public.document_chunks TO postgres;

\echo 'Fix completed. Showing final status...'

-- Final verification
SELECT 'public.document_chunks' as table_location, COUNT(*) as record_count
FROM public.document_chunks
WHERE EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'document_chunks');

-- Show column structure
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'document_chunks'
ORDER BY ordinal_position;

\echo 'Schema fix completed successfully!'
\echo 'Your application should now be able to find public.document_chunks with all categorization columns.'