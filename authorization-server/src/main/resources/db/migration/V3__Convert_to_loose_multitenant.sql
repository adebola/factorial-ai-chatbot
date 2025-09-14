-- Migration to convert from strict-multitenant to loose-multitenant pattern
-- This ensures global user uniqueness across all tenants

-- =============================================================================
-- STEP 1: DROP TENANT-SCOPED UNIQUE CONSTRAINTS
-- =============================================================================

-- Drop existing tenant-scoped unique constraints
ALTER TABLE users DROP CONSTRAINT IF EXISTS uk_users_tenant_username;
ALTER TABLE users DROP CONSTRAINT IF EXISTS uk_users_tenant_email;

-- =============================================================================
-- STEP 2: ADD GLOBAL UNIQUE CONSTRAINTS  
-- =============================================================================

-- Make email globally unique across all tenants (primary for loose-multitenant)
ALTER TABLE users ADD CONSTRAINT uk_users_email_global UNIQUE(email);

-- Make username globally unique as well to prevent conflicts
ALTER TABLE users ADD CONSTRAINT uk_users_username_global UNIQUE(username);

-- =============================================================================
-- STEP 3: ADD HELPER FUNCTIONS FOR INVITATION CONFLICTS
-- =============================================================================

-- Function to generate unique email for invitations when conflicts occur
-- This will append @domain.ext suffix to handle email conflicts
CREATE OR REPLACE FUNCTION generate_unique_invitation_email(
    original_email VARCHAR(255),
    tenant_domain VARCHAR(255)
) RETURNS VARCHAR(255) AS $$
DECLARE
    base_email VARCHAR(255);
    domain_part VARCHAR(255);
    counter INTEGER := 1;
    candidate_email VARCHAR(255);
    at_position INTEGER;
BEGIN
    -- Extract email parts
    at_position := POSITION('@' IN original_email);
    IF at_position = 0 THEN
        RAISE EXCEPTION 'Invalid email format: %', original_email;
    END IF;
    
    base_email := SUBSTRING(original_email FROM 1 FOR at_position - 1);
    domain_part := SUBSTRING(original_email FROM at_position);
    
    -- Try variations until we find a unique one
    LOOP
        IF counter = 1 THEN
            -- First try: append tenant domain
            candidate_email := base_email || '+' || tenant_domain || domain_part;
        ELSE
            -- Subsequent tries: add counter
            candidate_email := base_email || '+' || tenant_domain || '.' || counter || domain_part;
        END IF;
        
        -- Check if this email is available
        IF NOT EXISTS (SELECT 1 FROM users WHERE email = candidate_email) THEN
            RETURN candidate_email;
        END IF;
        
        counter := counter + 1;
        
        -- Safety check to prevent infinite loop
        IF counter > 100 THEN
            RAISE EXCEPTION 'Could not generate unique email after 100 attempts for: %', original_email;
        END IF;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- STEP 4: ADD HELPER FUNCTION FOR USERNAME CONFLICTS
-- =============================================================================

-- Function to generate unique username when conflicts occur
CREATE OR REPLACE FUNCTION generate_unique_username(
    original_username VARCHAR(255),
    tenant_domain VARCHAR(255)
) RETURNS VARCHAR(255) AS $$
DECLARE
    counter INTEGER := 1;
    candidate_username VARCHAR(255);
BEGIN
    -- Try variations until we find a unique one
    LOOP
        IF counter = 1 THEN
            -- First try: append tenant domain
            candidate_username := original_username || '.' || tenant_domain;
        ELSE
            -- Subsequent tries: add counter
            candidate_username := original_username || '.' || tenant_domain || '.' || counter;
        END IF;
        
        -- Ensure it doesn't exceed length limit
        IF LENGTH(candidate_username) > 255 THEN
            -- Truncate original username and retry
            candidate_username := SUBSTRING(original_username FROM 1 FOR 200) || '.' || tenant_domain || '.' || counter;
        END IF;
        
        -- Check if this username is available
        IF NOT EXISTS (SELECT 1 FROM users WHERE username = candidate_username) THEN
            RETURN candidate_username;
        END IF;
        
        counter := counter + 1;
        
        -- Safety check to prevent infinite loop
        IF counter > 100 THEN
            RAISE EXCEPTION 'Could not generate unique username after 100 attempts for: %', original_username;
        END IF;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- STEP 5: UPDATE INDEXES FOR GLOBAL LOOKUPS
-- =============================================================================

-- Drop old tenant-scoped indexes that are no longer optimal
DROP INDEX IF EXISTS idx_users_username;
DROP INDEX IF EXISTS idx_users_email;

-- Create new indexes optimized for global user lookups
CREATE UNIQUE INDEX idx_users_email_global ON users(email);
CREATE UNIQUE INDEX idx_users_username_global ON users(username);
CREATE INDEX idx_users_email_active ON users(email) WHERE is_active = true;
CREATE INDEX idx_users_username_active ON users(username) WHERE is_active = true;

-- Keep tenant-specific indexes for tenant management queries
CREATE INDEX idx_users_tenant_email ON users(tenant_id, email);
CREATE INDEX idx_users_tenant_username ON users(tenant_id, username);

-- =============================================================================
-- STEP 6: ADD COMMENTS FOR DOCUMENTATION
-- =============================================================================

COMMENT ON CONSTRAINT uk_users_email_global ON users IS 'Global email uniqueness for loose-multitenant pattern';
COMMENT ON CONSTRAINT uk_users_username_global ON users IS 'Global username uniqueness for loose-multitenant pattern';

COMMENT ON FUNCTION generate_unique_invitation_email(VARCHAR, VARCHAR) IS 'Generates unique email for invitations when original email conflicts exist';
COMMENT ON FUNCTION generate_unique_username(VARCHAR, VARCHAR) IS 'Generates unique username when original username conflicts exist';

-- =============================================================================
-- VERIFICATION QUERIES (FOR TESTING)
-- =============================================================================

-- The following queries can be used to verify the migration worked correctly:
-- 
-- 1. Check that global unique constraints exist:
-- SELECT constraint_name, constraint_type 
-- FROM information_schema.table_constraints 
-- WHERE table_name = 'users' AND constraint_type = 'UNIQUE';
--
-- 2. Test the email generation function:
-- SELECT generate_unique_invitation_email('john@company.com', 'acme-corp');
--
-- 3. Test global user lookup (should work without tenant context):
-- SELECT u.*, t.name as tenant_name 
-- FROM users u JOIN tenants t ON u.tenant_id = t.id 
-- WHERE u.email = 'admin@example.com';