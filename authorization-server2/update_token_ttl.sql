-- Update Token TTL Settings for OAuth2 Registered Client
--
-- This script updates the existing registered client to use:
-- - Access Token TTL: 5 minutes (PT5M)
-- - Refresh Token TTL: 1 hour (PT1H)
--
-- Execute this against the authorization_db2 database

-- First, check the current state
SELECT
    id,
    client_id,
    client_name,
    token_settings,
    is_active,
    created_at,
    updated_at
FROM registered_clients
WHERE is_active = true;

-- Update the token settings
UPDATE registered_clients
SET
    token_settings = '{"accessTokenTimeToLive":"PT5M","refreshTokenTimeToLive":"PT1H"}',
    updated_at = NOW()
WHERE is_active = true;

-- Verify the update
SELECT
    id,
    client_id,
    client_name,
    token_settings,
    is_active,
    created_at,
    updated_at
FROM registered_clients
WHERE is_active = true;

-- Note: After running this update, you should:
-- 1. Clear the Redis cache OR restart the authorization server
-- 2. Test token generation to verify new TTL values
-- 3. Access tokens will now expire after 5 minutes
-- 4. Refresh tokens will now expire after 1 hour
