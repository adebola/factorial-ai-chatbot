-- 09-add-fulltext-to-chunks.sql
--
-- Add lexical (full-text) search to the document_chunks table so the chat
-- service can run a parallel keyword leg alongside vector similarity. This
-- catches literal-match queries (e.g. "careers", "embryologist") that vector
-- search misses when relevant content is buried in a chunk dominated by other
-- semantic content.
--
-- Pair this migration with the hybrid retrieval logic in
-- chat-service/app/services/pg_vector_store.py (Reciprocal Rank Fusion).

\c vector_db;

-- btree_gin lets us combine btree columns (tenant_id) with GIN-indexed
-- columns (content_tsv) in a single index for cheap per-tenant FTS scans.
CREATE EXTENSION IF NOT EXISTS btree_gin;

-- Generated tsvector derived from the chunk content. STORED so reads are
-- index-only and we never recompute at query time.
ALTER TABLE vectors.document_chunks
    ADD COLUMN IF NOT EXISTS content_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', coalesce(content, ''))) STORED;

-- GIN index for fast @@ matching. Also create the compound (tenant_id,
-- content_tsv) variant so per-tenant FTS doesn't seq-scan the table.
CREATE INDEX IF NOT EXISTS idx_document_chunks_content_tsv
    ON vectors.document_chunks USING GIN (content_tsv);

CREATE INDEX IF NOT EXISTS idx_document_chunks_tenant_content_tsv
    ON vectors.document_chunks USING GIN (tenant_id, content_tsv);

\echo '✓ content_tsv column + GIN indexes added to vectors.document_chunks'
