-- Migration to enhance a tenant model and add default OAuth2 client
-- V3__Enhance_tenant_model_and_add_default_client.sql

-- First, enhance the tenants table with missing fields to match onboarding service
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS api_key VARCHAR(255);
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS website_url VARCHAR(500);
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS username VARCHAR(255);
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS email VARCHAR(255);
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255);
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS role VARCHAR(50);
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS config TEXT; -- JSON config as text
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS plan_id VARCHAR(36);

-- Add unique constraints where appropriate (PostgreSQL compatible syntax)
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uk_tenants_api_key') THEN
        ALTER TABLE tenants ADD CONSTRAINT uk_tenants_api_key UNIQUE (api_key);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uk_tenants_username') THEN
        ALTER TABLE tenants ADD CONSTRAINT uk_tenants_username UNIQUE (username);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uk_tenants_email') THEN
        ALTER TABLE tenants ADD CONSTRAINT uk_tenants_email UNIQUE (email);
    END IF;
END $$;

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_tenants_api_key ON tenants(api_key);
CREATE INDEX IF NOT EXISTS idx_tenants_username ON tenants(username);
CREATE INDEX IF NOT EXISTS idx_tenants_email ON tenants(email);

-- Insert default OAuth2 client for system
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
    is_active,
    created_at,
    updated_at
) VALUES (
    'default-webclient-id',
    'webclient',
    '$2a$10$5oKw8aKs8bE8Ux8rKVJ5kuOKKe5XQzJJ5r1t5VkL9D8Z8gU5pKx4W', -- bcrypt of 'webclient-secret'
    'Default Web Client',
    'client_secret_basic,client_secret_post',
    'authorization_code,refresh_token,client_credentials',
    'http://localhost:4200/callback,https://your-domain.com/callback',
    'http://localhost:4200/logout,https://your-domain.com/logout',
    'openid,profile,read,write',
    '{"requireAuthorizationConsent":false,"requireProofKey":true}',
    '{"accessTokenTimeToLive":"PT1H","refreshTokenTimeToLive":"P30D"}',
    false,
    true,
    true,
    NOW(),
    NOW()
) ON CONFLICT (client_id) DO NOTHING;

-- Update comment
COMMENT ON TABLE tenants IS 'Enhanced tenant table with OAuth2 and user management fields';
COMMENT ON TABLE registered_clients IS 'OAuth2 registered clients - single default client system';