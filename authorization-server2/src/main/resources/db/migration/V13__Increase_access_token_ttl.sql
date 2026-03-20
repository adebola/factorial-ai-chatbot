-- =====================================================================================
-- V13: Increase Access Token TTL from 5 to 15 Minutes
-- =====================================================================================
-- Purpose:
--   Users building workflows in the UI lose their work when the access token
--   expires after 5 minutes. Increasing TTL to 15 minutes gives enough time
--   to complete and save workflow entries.
--
-- Change:
--   - webclient access token TTL: PT5M → PT15M
--   - webclient refresh token TTL: unchanged (PT1H)
-- =====================================================================================

UPDATE registered_clients
SET token_settings = '{"accessTokenTimeToLive":"PT15M","refreshTokenTimeToLive":"PT1H"}',
    updated_at = NOW()
WHERE client_id = 'webclient';
