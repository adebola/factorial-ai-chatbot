-- Migration to add subscription_id column to tenants table
-- This tracks the billing service subscription ID for each tenant
-- V9__Add_subscription_id_to_tenants.sql

-- Add subscription_id column to track billing service subscriptions
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS subscription_id VARCHAR(36);

-- Add index for performance
CREATE INDEX IF NOT EXISTS idx_tenants_subscription_id ON tenants(subscription_id);

-- Add comment
COMMENT ON COLUMN tenants.subscription_id IS 'Billing service subscription ID - references subscriptions table in billing_db';
