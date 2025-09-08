-- Migration to remove websiteUrl and description fields from tenants table
-- V5__Remove_websiteurl_and_description_from_tenants.sql

-- Drop the website_url and description columns that are no longer needed
ALTER TABLE tenants DROP COLUMN IF EXISTS website_url;
ALTER TABLE tenants DROP COLUMN IF EXISTS description;

-- Update comment
COMMENT ON TABLE tenants IS 'Simplified tenant table with essential fields only - removed websiteUrl and description';