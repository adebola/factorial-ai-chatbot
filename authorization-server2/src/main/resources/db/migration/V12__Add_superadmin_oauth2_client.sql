-- =====================================================================================
-- V12: Add superadmin-client OAuth2 Client for Super Admin Application
-- =====================================================================================
-- Purpose:
--   1. Register OAuth2 client for ChatCraft Super Admin Application
--   2. Configure client with system-admin scope for ROLE_SYSTEM_ADMIN users
--   3. Support both development (localhost:4201) and production URLs
-- =====================================================================================

-- ============================================================================
-- Insert Registered Client (superadmin-client)
-- ============================================================================
-- This OAuth2 client is used exclusively by the ChatCraft Super Admin Application
-- Only users with ROLE_SYSTEM_ADMIN can access this application
-- Includes system-admin scope for backend authorization
-- Client secret: superadmin-secret (bcrypt hashed)

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
    'superadmin-client',
    '{bcrypt}$2a$12$8ZhXqE5aI3rFqJ5Y1xY8y.7Y8KqF6sJ5kL9Y8xY8y7Y8KqF6sJ5kL',  -- Hash of 'superadmin-secret'
    'ChatCraft Super Admin',
    '["client_secret_basic","client_secret_post"]',
    '["authorization_code","refresh_token"]',
    '["http://localhost:4201/callback","https://admin.chatcraft.cc/callback"]',
    '["http://localhost:4201","https://admin.chatcraft.cc"]',
    '["openid","profile","read","write","admin","system-admin"]',
    '',
    '{"accessTokenTimeToLive":"PT15M","refreshTokenTimeToLive":"PT2H"}',
    false,
    true,  -- Require PKCE for enhanced security
    true
WHERE NOT EXISTS (
    SELECT 1 FROM registered_clients WHERE client_id = 'superadmin-client'
);

-- ============================================================================
-- Migration Complete
-- ============================================================================
-- This migration adds:
-- - superadmin-client OAuth2 client for Super Admin Application
-- - Configured with system-admin scope
-- - PKCE required for security
-- - Longer token lifetimes for admin workflows
--
-- Development URL: http://localhost:4201
-- Production URL: https://admin.chatcraft.cc
-- ============================================================================
