-- V7: Add company logo URL column to tenant_settings table

-- Add company logo URL column
ALTER TABLE tenant_settings 
ADD COLUMN company_logo_url VARCHAR(500);

-- Add comment for documentation  
COMMENT ON COLUMN tenant_settings.company_logo_url IS 'URL of the company logo for branding (served via OAuth2 proxy endpoint)';

-- Optional: Create index if needed for logo queries
CREATE INDEX idx_tenant_settings_logo_url ON tenant_settings (company_logo_url);