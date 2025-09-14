-- Migration to remove user-related fields from tenants table
-- V4__Remove_user_fields_from_tenants.sql

-- Drop unique constraints first (if they exist)
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uk_tenants_username') THEN
        ALTER TABLE tenants DROP CONSTRAINT uk_tenants_username;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uk_tenants_email') THEN
        ALTER TABLE tenants DROP CONSTRAINT uk_tenants_email;
    END IF;
END $$;

-- Drop indexes
DROP INDEX IF EXISTS idx_tenants_username;
DROP INDEX IF EXISTS idx_tenants_email;

-- Drop the user-related columns that have been migrated to users table
ALTER TABLE tenants DROP COLUMN IF EXISTS username;
ALTER TABLE tenants DROP COLUMN IF EXISTS email;
ALTER TABLE tenants DROP COLUMN IF EXISTS password_hash;
ALTER TABLE tenants DROP COLUMN IF EXISTS role;

-- Update comment
COMMENT ON TABLE tenants IS 'Tenant table with OAuth2 fields - user fields migrated to users table';