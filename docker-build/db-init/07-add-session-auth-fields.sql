-- 07: Add end-user OAuth2 PKCE authentication fields to chat_sessions
-- These fields store identity info for authenticated sessions.
-- Actual tokens (access_token, refresh_token) are stored in Redis, not here.

ALTER TABLE chat_sessions
  ADD COLUMN IF NOT EXISTS is_authenticated BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS auth_user_sub VARCHAR(255),
  ADD COLUMN IF NOT EXISTS auth_user_email VARCHAR(255),
  ADD COLUMN IF NOT EXISTS auth_user_name VARCHAR(255);

COMMENT ON COLUMN chat_sessions.is_authenticated IS 'Whether this session was created via OAuth2 PKCE login';
COMMENT ON COLUMN chat_sessions.auth_user_sub IS 'Subject claim from the end-user IdP token';
COMMENT ON COLUMN chat_sessions.auth_user_email IS 'Email from the end-user IdP token';
COMMENT ON COLUMN chat_sessions.auth_user_name IS 'Display name from the end-user IdP token';
