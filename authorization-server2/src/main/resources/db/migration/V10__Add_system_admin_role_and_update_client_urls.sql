-- =====================================================================================
-- V10: Add SYSTEM_ADMIN role and insert registered_clients for production
-- =====================================================================================
-- Purpose:
--   1. Ensure TENANT_ADMIN role exists (may have been created in V1 or manually)
--   2. Add SYSTEM_ADMIN role to roles table (new cross-tenant admin role)
--   3. Insert webclient registered_client with production URLs
--   4. Idempotent - safe to run on both dev (with existing data) and prod (empty)
-- =====================================================================================

-- ============================================================================
-- Part 1: Ensure TENANT_ADMIN Role Exists
-- ============================================================================
-- TENANT_ADMIN may have been created in V1 or entered manually
-- This ensures it exists in production database

INSERT INTO roles (id, name, description, is_active)
SELECT
    '550e8400-e29b-41d4-a716-446655440002',
    'TENANT_ADMIN',
    'Tenant administrator with tenant-level access',
    true
WHERE NOT EXISTS (
    SELECT 1 FROM roles WHERE name = 'TENANT_ADMIN'
);

-- ============================================================================
-- Part 2: Add SYSTEM_ADMIN Role
-- ============================================================================
-- SYSTEM_ADMIN is a new role for cross-tenant system administration
-- This role has full system-wide access across all tenants

INSERT INTO roles (id, name, description, is_active)
SELECT
    '550e8400-e29b-41d4-a716-446655440003',
    'SYSTEM_ADMIN',
    'System administrator with full system-wide access across all tenants',
    true
WHERE NOT EXISTS (
    SELECT 1 FROM roles WHERE name = 'SYSTEM_ADMIN'
);

-- ============================================================================
-- Part 3: Insert Registered Client (webclient) with Production URLs
-- ============================================================================
-- This inserts the OAuth2 client configuration for the web application
-- Uses production URLs (https://app.chatcraft.cc) instead of localhost
-- The client_secret is bcrypt hashed
-- Conditional insert - only if webclient doesn't already exist

INSERT INTO registered_clients (
    id,
    client_id,
    client_secret,
    client_name,
    client_authentication_methods,
    authorization_grant_types,
    redirect_uris,
    post_logout_redirect_uris,
    scopes,
    client_settings,
    token_settings,
    require_authorization_consent,
    require_proof_key,
    is_active
)
SELECT
    gen_random_uuid()::text,
    'webclient',
    '{bcrypt}$2a$12$r0K6mySqM.Myc/EPJL55zOsCzboTNWUfibLF4J8NQKq3BDRvomyHu',
    'webclient for chatcraft',
    '["client_secret_basic"]',
    '["authorization_code","refresh_token","password","client_credentials"]',
    '["https://app.chatcraft.cc/callback"]',
    '["https://app.chatcraft.cc","https://app.chatcraft.cc/logout"]',
    '["openid","profile", "read", "write"]',
    '',
    '{"accessTokenTimeToLive":"PT5M","refreshTokenTimeToLive":"PT1H"}',
    false,
    false,
    true
WHERE NOT EXISTS (
    SELECT 1 FROM registered_clients WHERE client_id = 'webclient'
);

-- ============================================================================
-- Migration Complete
-- ============================================================================
-- This migration adds:
-- - TENANT_ADMIN role (if not exists)
-- - SYSTEM_ADMIN role (if not exists)
-- - webclient OAuth2 client (if not exists) with production URLs
--
-- Safe to run on:
-- - Development database (with existing manual data) - skips duplicates
-- - Production database (empty) - inserts all records fresh
-- ============================================================================
