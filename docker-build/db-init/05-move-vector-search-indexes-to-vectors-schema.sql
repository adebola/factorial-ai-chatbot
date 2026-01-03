-- =============================================================================
-- Move vector_search_indexes from public to vectors schema
-- =============================================================================
-- This script moves the vector_search_indexes table from public schema to
-- vectors schema to match production and code expectations.
--
-- Run manually on development:
-- PGPASSWORD=password psql -h localhost -U postgres -d vector_db -f 05-move-vector-search-indexes-to-vectors-schema.sql
--
-- Purpose:
-- - Ensure both vector tables are in the same schema (vectors)
-- - Match production schema structure
-- - Fix any schema mismatch issues in development
--
-- Safe to run multiple times (checks if migration needed)
-- =============================================================================

\c vector_db;

\echo '========================================='
\echo 'Move vector_search_indexes to vectors schema'
\echo '========================================='

-- =============================================================================
-- STEP 1: Check current state
-- =============================================================================
\echo ''
\echo 'Step 1: Checking current table locations...'

DO $$
DECLARE
    table_in_public BOOLEAN;
    table_in_vectors BOOLEAN;
BEGIN
    -- Check if table exists in public schema
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'vector_search_indexes'
    ) INTO table_in_public;

    -- Check if table exists in vectors schema
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'vectors' AND table_name = 'vector_search_indexes'
    ) INTO table_in_vectors;

    -- Report status
    IF table_in_public AND NOT table_in_vectors THEN
        RAISE NOTICE '⚠️  Table found in public schema - MIGRATION NEEDED';
    ELSIF NOT table_in_public AND table_in_vectors THEN
        RAISE NOTICE '✓ Table already in vectors schema - NO MIGRATION NEEDED';
    ELSIF table_in_public AND table_in_vectors THEN
        RAISE NOTICE '⚠️  Table exists in BOTH schemas - will consolidate';
    ELSE
        RAISE NOTICE '⚠️  Table not found in either schema - will create in vectors';
    END IF;
END $$;

-- =============================================================================
-- STEP 2: Ensure vectors schema exists
-- =============================================================================
\echo ''
\echo 'Step 2: Ensuring vectors schema exists...'

CREATE SCHEMA IF NOT EXISTS vectors;
GRANT ALL ON SCHEMA vectors TO postgres;

\echo '✓ vectors schema ready'

-- =============================================================================
-- STEP 3: Create table in vectors schema if it doesn't exist
-- =============================================================================
\echo ''
\echo 'Step 3: Creating table in vectors schema (if needed)...'

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

\echo '✓ Table exists in vectors schema'

-- =============================================================================
-- STEP 4: Migrate data from public to vectors (if needed)
-- =============================================================================
\echo ''
\echo 'Step 4: Migrating data from public to vectors (if needed)...'

DO $$
DECLARE
    table_in_public BOOLEAN;
    record_count INTEGER;
BEGIN
    -- Check if table exists in public schema
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'vector_search_indexes'
    ) INTO table_in_public;

    IF table_in_public THEN
        -- Count records in public schema
        EXECUTE 'SELECT COUNT(*) FROM public.vector_search_indexes' INTO record_count;
        RAISE NOTICE 'Found % records in public.vector_search_indexes', record_count;

        IF record_count > 0 THEN
            -- Copy data from public to vectors (avoiding duplicates)
            RAISE NOTICE 'Copying data to vectors.vector_search_indexes...';
            INSERT INTO vectors.vector_search_indexes
            SELECT * FROM public.vector_search_indexes
            ON CONFLICT (tenant_id) DO UPDATE SET
                total_chunks = EXCLUDED.total_chunks,
                last_indexed_at = EXCLUDED.last_indexed_at,
                index_version = EXCLUDED.index_version,
                avg_query_time_ms = EXCLUDED.avg_query_time_ms,
                last_optimized_at = EXCLUDED.last_optimized_at,
                updated_at = EXCLUDED.updated_at;

            RAISE NOTICE '✓ Data migrated successfully';
        ELSE
            RAISE NOTICE 'No data to migrate';
        END IF;
    ELSE
        RAISE NOTICE 'No table in public schema - nothing to migrate';
    END IF;
END $$;

-- =============================================================================
-- STEP 5: Create indexes
-- =============================================================================
\echo ''
\echo 'Step 5: Creating indexes...'

CREATE INDEX IF NOT EXISTS idx_search_indexes_tenant
ON vectors.vector_search_indexes (tenant_id);

\echo '✓ Indexes created'

-- =============================================================================
-- STEP 6: Grant permissions
-- =============================================================================
\echo ''
\echo 'Step 6: Granting permissions...'

GRANT ALL ON TABLE vectors.vector_search_indexes TO postgres;

\echo '✓ Permissions granted'

-- =============================================================================
-- STEP 7: Drop old table from public schema (if exists)
-- =============================================================================
\echo ''
\echo 'Step 7: Cleaning up old public schema table...'

DO $$
DECLARE
    table_in_public BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'vector_search_indexes'
    ) INTO table_in_public;

    IF table_in_public THEN
        RAISE NOTICE 'Dropping public.vector_search_indexes...';
        DROP TABLE public.vector_search_indexes CASCADE;
        RAISE NOTICE '✓ Old table dropped';
    ELSE
        RAISE NOTICE 'No table in public schema to drop';
    END IF;
END $$;

-- =============================================================================
-- STEP 8: Verification
-- =============================================================================
\echo ''
\echo '========================================='
\echo 'Verification and Status Report'
\echo '========================================='

-- Check final state
\echo ''
\echo 'Final Table Location:'
SELECT
    CASE
        WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'vectors' AND table_name = 'vector_search_indexes')
        THEN '✓ vectors.vector_search_indexes EXISTS'
        ELSE '✗ ERROR: vectors.vector_search_indexes DOES NOT EXIST'
    END as vectors_schema_status;

SELECT
    CASE
        WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'vector_search_indexes')
        THEN '✗ WARNING: public.vector_search_indexes still exists (should have been dropped)'
        ELSE '✓ public.vector_search_indexes does not exist (correct)'
    END as public_schema_status;

-- Show table structure
\echo ''
\echo 'Table Structure:'
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'vectors' AND table_name = 'vector_search_indexes'
ORDER BY ordinal_position;

-- Show indexes
\echo ''
\echo 'Indexes:'
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'vector_search_indexes' AND schemaname = 'vectors'
ORDER BY indexname;

-- Show record count
\echo ''
\echo 'Record Count:'
SELECT COUNT(*) as total_records FROM vectors.vector_search_indexes;

\echo ''
\echo '========================================='
\echo '✓ Migration COMPLETED!'
\echo '========================================='
\echo ''
\echo 'Summary:'
\echo '- vectors.vector_search_indexes is now in correct schema'
\echo '- Data migrated from public schema (if any existed)'
\echo '- Old public.vector_search_indexes table dropped'
\echo '- Indexes and permissions configured'
\echo ''
\echo 'Your development environment now matches production!'
\echo '========================================='
