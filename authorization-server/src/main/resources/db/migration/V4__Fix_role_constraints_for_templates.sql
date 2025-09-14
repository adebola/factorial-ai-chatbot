-- Fix role constraints to allow template roles
-- Template roles need is_global=false and tenant_id=null which the original constraint didn't allow

-- =============================================================================
-- DROP THE RESTRICTIVE CONSTRAINT
-- =============================================================================

-- Remove the constraint that prevents template roles
ALTER TABLE roles DROP CONSTRAINT IF EXISTS chk_global_role_no_tenant;

-- =============================================================================
-- ADD A MORE FLEXIBLE CONSTRAINT
-- =============================================================================

-- New constraint that allows:
-- 1. Global roles: is_global=true AND tenant_id IS NULL
-- 2. Tenant roles: is_global=false AND tenant_id IS NOT NULL  
-- 3. Template roles: is_global=false AND tenant_id IS NULL AND name LIKE '%_TEMPLATE'
ALTER TABLE roles ADD CONSTRAINT chk_role_tenant_logic CHECK (
    -- Global roles must have no tenant
    (is_global = true AND tenant_id IS NULL) OR
    -- Regular tenant roles must have a tenant
    (is_global = false AND tenant_id IS NOT NULL) OR
    -- Template roles must be non-global, have no tenant, and end with _TEMPLATE
    (is_global = false AND tenant_id IS NULL AND name LIKE '%_TEMPLATE')
);

-- =============================================================================
-- ADD COMMENT FOR DOCUMENTATION
-- =============================================================================

COMMENT ON CONSTRAINT chk_role_tenant_logic ON roles IS 
'Ensures proper role categorization: global roles (no tenant), tenant roles (with tenant), template roles (no tenant but name ends with _TEMPLATE)';

-- =============================================================================
-- FIX TEMPLATE ROLES (from V2 workaround)
-- =============================================================================

-- Convert template roles from global=true (workaround) back to global=false (correct)
UPDATE roles 
SET is_global = false 
WHERE name LIKE '%_TEMPLATE' AND is_global = true;

-- =============================================================================
-- VERIFY CONSTRAINT WORKS WITH EXISTING ROLES
-- =============================================================================

-- This query can be used to verify the constraint logic:
-- SELECT name, is_global, tenant_id, 
--        CASE 
--            WHEN is_global = true AND tenant_id IS NULL THEN 'Global Role'
--            WHEN is_global = false AND tenant_id IS NOT NULL THEN 'Tenant Role'
--            WHEN is_global = false AND tenant_id IS NULL AND name LIKE '%_TEMPLATE' THEN 'Template Role'
--            ELSE 'Invalid Role Configuration'
--        END as role_type
-- FROM roles;