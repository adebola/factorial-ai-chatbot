-- V11: Make domain column nullable
-- This allows tenants to be created without a domain, simplifying registration

-- Remove NOT NULL constraint from domain column
ALTER TABLE tenants ALTER COLUMN domain DROP NOT NULL;

-- Drop unique constraint if it exists (domain can still be unique when present, but NULL values allowed)
-- Note: PostgreSQL allows multiple NULL values in a unique column
-- The unique constraint will still prevent duplicate non-NULL domains
