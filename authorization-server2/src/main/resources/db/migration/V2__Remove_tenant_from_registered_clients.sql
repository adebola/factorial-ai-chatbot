-- Migration to remove tenant_id from registered_clients table for simplified single-client architecture
-- V2__Remove_tenant_from_registered_clients.sql

-- Remove existing data first as we're changing the architecture
DELETE FROM registered_clients;

-- Remove the tenant_id column and foreign key constraint
ALTER TABLE registered_clients DROP COLUMN IF EXISTS tenant_id;

-- Update the table to reflect single-client architecture
COMMENT ON TABLE registered_clients IS 'OAuth2 registered client - single client per system';