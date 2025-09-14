-- Insert Essential Default Roles for Multi-Tenant OAuth2 System
-- This migration creates the basic roles needed for the system

-- =============================================================================
-- TEMPLATE ROLES (Used as blueprints for tenant creation)
-- =============================================================================

-- Tenant Admin Role Template - Will be copied for each tenant during registration
-- WORKAROUND: Temporarily make this global to satisfy constraint, will be fixed in V4
INSERT INTO roles (
    id, 
    name, 
    description, 
    is_global, 
    tenant_id, 
    permissions,
    is_active,
    created_at,
    updated_at
) VALUES (
    uuid_generate_v4(),
    'TENANT_ADMIN_TEMPLATE',
    'Template for tenant administrator role - copied during tenant creation',
    true,  -- TEMPORARY: Will be changed to false in V4
    null, -- null tenant_id indicates this is a template
    '[
        "tenant:manage",
        "users:create",
        "users:read", 
        "users:update",
        "users:delete",
        "users:invite",
        "roles:assign",
        "documents:manage",
        "chat:access",
        "settings:manage"
    ]'::jsonb,
    true,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
);

-- Tenant User Role Template - Will be copied for each tenant during registration  
-- WORKAROUND: Temporarily make this global to satisfy constraint, will be fixed in V4
INSERT INTO roles (
    id, 
    name, 
    description, 
    is_global, 
    tenant_id, 
    permissions,
    is_active,
    created_at,
    updated_at
) VALUES (
    uuid_generate_v4(),
    'TENANT_USER_TEMPLATE', 
    'Template for regular tenant user role - copied during tenant creation',
    true,  -- TEMPORARY: Will be changed to false in V4
    null, -- null tenant_id indicates this is a template
    '[
        "documents:read",
        "chat:access",
        "profile:update"
    ]'::jsonb,
    true,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
);

-- =============================================================================
-- GLOBAL SYSTEM ROLES
-- =============================================================================

-- Global Admin Role - System super administrator
INSERT INTO roles (
    id, 
    name, 
    description, 
    is_global, 
    tenant_id, 
    permissions,
    is_active,
    created_at,
    updated_at
) VALUES (
    uuid_generate_v4(),
    'GLOBAL_ADMIN',
    'Global system administrator with full access to all tenants and system configuration',
    true,
    null,
    '[
        "system:manage",
        "tenants:create",
        "tenants:read",
        "tenants:update", 
        "tenants:delete",
        "users:manage_all",
        "roles:manage_all",
        "oauth:manage_clients",
        "audit:read_all"
    ]'::jsonb,
    true,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
);

-- =============================================================================
-- COMMENTS FOR DOCUMENTATION
-- =============================================================================

COMMENT ON TABLE roles IS 'System roles including both templates and actual roles';

-- Standard permissions:
-- system:manage - Full system administration
-- tenants:create/read/update/delete - Tenant management
-- users:create/read/update/delete/manage_all/invite - User management
-- roles:assign/manage_all - Role management  
-- documents:read/manage - Document access
-- chat:access - Chat functionality
-- settings:manage - Tenant settings
-- oauth:manage_clients - OAuth2 client management
-- audit:read_all - Audit log access
-- profile:update - Personal profile updates