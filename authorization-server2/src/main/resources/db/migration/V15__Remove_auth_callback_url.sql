-- Remove tenant-configurable auth_callback_url column
-- The callback URL is now always derived from the platform gateway URL: {gatewayUrl}/api/v1/auth/callback
ALTER TABLE tenant_settings DROP COLUMN IF EXISTS auth_callback_url;
