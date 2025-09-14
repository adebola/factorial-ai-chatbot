-- Simplify roles system - make all roles global and remove parent-child relationships
-- This migration removes the complexity of tenant-specific roles and role hierarchy

-- =============================================================================
-- STEP 1: REMOVE PARENT-CHILD RELATIONSHIP CONSTRAINTS AND COLUMNS
-- =============================================================================

-- Drop foreign key constraint for parent roles (if exists)
ALTER TABLE roles DROP CONSTRAINT IF EXISTS roles_parent_role_id_fkey;

-- Remove parent role column (no more hierarchy)
ALTER TABLE roles DROP COLUMN IF EXISTS parent_role_id;

-- =============================================================================
-- STEP 2: SIMPLIFY TENANT-RELATED CONSTRAINTS AND COLUMNS
-- =============================================================================

-- Drop the complex constraint we created earlier
ALTER TABLE roles DROP CONSTRAINT IF EXISTS chk_role_tenant_logic;
ALTER TABLE roles DROP CONSTRAINT IF EXISTS chk_global_role_no_tenant;

-- Remove tenant-related columns since all roles are now global
ALTER TABLE roles DROP COLUMN IF EXISTS tenant_id;
ALTER TABLE roles DROP COLUMN IF EXISTS is_global;

-- =============================================================================
-- STEP 3: UPDATE EXISTING ROLES TO REMOVE TEMPLATE SUFFIX
-- =============================================================================

-- Remove _TEMPLATE suffix from role names since we don't need templates anymore
UPDATE roles 
SET name = REPLACE(name, '_TEMPLATE', '')
WHERE name LIKE '%_TEMPLATE';

-- =============================================================================
-- STEP 4: ADD SIMPLIFIED CONSTRAINTS
-- =============================================================================

-- Ensure role names are unique (since all roles are global now)
ALTER TABLE roles DROP CONSTRAINT IF EXISTS uk_roles_name_tenant;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uk_roles_name' AND conrelid = 'roles'::regclass) THEN
        ALTER TABLE roles ADD CONSTRAINT uk_roles_name UNIQUE(name);
    END IF;
END
$$;

-- Ensure role name is not empty
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_role_name_not_empty' AND conrelid = 'roles'::regclass) THEN
        ALTER TABLE roles ADD CONSTRAINT chk_role_name_not_empty CHECK (LENGTH(TRIM(name)) > 0);
    END IF;
END
$$;

-- Ensure permissions array exists and is valid JSON
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_role_permissions_valid' AND conrelid = 'roles'::regclass) THEN
        ALTER TABLE roles ADD CONSTRAINT chk_role_permissions_valid CHECK (
            permissions IS NOT NULL AND 
            jsonb_typeof(permissions) = 'array'
        );
    END IF;
END
$$;

-- =============================================================================
-- STEP 5: ADD STANDARD GLOBAL ROLES (if not exist)
-- =============================================================================

-- Insert basic global roles if they don't exist
INSERT INTO roles (
    id, name, description, permissions, is_active, created_at, updated_at
) VALUES 
(
    uuid_generate_v4(),
    'ADMIN',
    'System administrator with full access',
    '[
        "system:manage",
        "users:create", "users:read", "users:update", "users:delete",
        "documents:create", "documents:read", "documents:update", "documents:delete",
        "chat:access", "chat:manage",
        "settings:manage",
        "roles:assign"
    ]'::jsonb,
    true,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
),
(
    uuid_generate_v4(),
    'USER',
    'Standard user with basic access',
    '[
        "documents:read", "documents:create",
        "chat:access",
        "profile:update"
    ]'::jsonb,
    true,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
),
(
    uuid_generate_v4(),
    'VIEWER',
    'Read-only access user',
    '[
        "documents:read",
        "chat:access"
    ]'::jsonb,
    true,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
)
ON CONFLICT (name) DO NOTHING; -- Don't insert if role already exists

-- =============================================================================
-- STEP 6: CLEAN UP INDEXES
-- =============================================================================

-- Drop old indexes that referenced removed columns
DROP INDEX IF EXISTS idx_roles_tenant_id;
DROP INDEX IF EXISTS idx_roles_is_global;

-- Create new indexes for the simplified structure
CREATE INDEX IF NOT EXISTS idx_roles_name ON roles(name) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_roles_is_active ON roles(is_active);
CREATE INDEX IF NOT EXISTS idx_roles_created_at ON roles(created_at);

-- =============================================================================
-- STEP 7: UPDATE COMMENTS
-- =============================================================================

COMMENT ON TABLE roles IS 'Global system roles - all roles are shared across all tenants';
COMMENT ON COLUMN roles.name IS 'Global role name (ADMIN, USER, VIEWER, etc.)';
COMMENT ON COLUMN roles.permissions IS 'JSON array of permission strings for this role';
COMMENT ON COLUMN roles.is_active IS 'Whether this role is active and can be assigned to users';

-- =============================================================================
-- VERIFICATION QUERY
-- =============================================================================

-- You can run this to verify the simplified structure:
-- SELECT name, description, jsonb_array_length(permissions) as permission_count, is_active 
-- FROM roles 
-- ORDER BY name;