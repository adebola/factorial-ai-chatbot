-- V14: Add OAuth2 PKCE end-user authentication configuration to tenant_settings
-- Allows tenants to enable OAuth2 PKCE authentication for their chat widget,
-- so end-users can log in via the tenant's Identity Provider before chatting.

ALTER TABLE tenant_settings
  ADD COLUMN allow_authentication BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN auth_authorization_endpoint VARCHAR(1000),
  ADD COLUMN auth_token_endpoint VARCHAR(1000),
  ADD COLUMN auth_client_id VARCHAR(255),
  ADD COLUMN auth_scopes VARCHAR(500) DEFAULT 'openid profile email',
  ADD COLUMN auth_callback_url VARCHAR(1000);

COMMENT ON COLUMN tenant_settings.allow_authentication IS 'Master toggle for end-user OAuth2 PKCE authentication in chat widget';
COMMENT ON COLUMN tenant_settings.auth_authorization_endpoint IS 'Tenant IdP OAuth2 authorization endpoint URL';
COMMENT ON COLUMN tenant_settings.auth_token_endpoint IS 'Tenant IdP OAuth2 token endpoint URL (server-side only)';
COMMENT ON COLUMN tenant_settings.auth_client_id IS 'OAuth2 client ID registered at tenant IdP';
COMMENT ON COLUMN tenant_settings.auth_scopes IS 'Space-separated OAuth2 scopes to request';
COMMENT ON COLUMN tenant_settings.auth_callback_url IS 'Redirect URI registered at the IdP (defaults to ChatCraft hosted callback)';
