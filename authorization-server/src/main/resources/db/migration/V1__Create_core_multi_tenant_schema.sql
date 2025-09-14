-- Multi-Tenant OAuth2 Authorization Server Schema
-- This migration creates the core tables for multi-tenant user management and OAuth2 support

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- CORE TENANT MANAGEMENT
-- =============================================================================

-- Tenants table - Each tenant represents an organization
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    domain VARCHAR(255) UNIQUE NOT NULL,
    client_id VARCHAR(255) UNIQUE NOT NULL, -- OAuth2 client identifier
    client_secret VARCHAR(255) NOT NULL,    -- Encrypted client secret
    callback_urls TEXT[], -- Array of allowed redirect URIs
    allowed_scopes TEXT[] DEFAULT ARRAY['openid', 'profile', 'documents:read', 'chat:access'], -- Allowed OAuth2 scopes
    is_active BOOLEAN DEFAULT true,
    plan_id UUID, -- Reference to subscription plan (future implementation)
    api_key VARCHAR(255) UNIQUE, -- Legacy API key for WebSocket connections
    
    -- Audit fields
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by UUID, -- Self-referencing to users table (nullable for system)
    
    -- Constraints
    CONSTRAINT chk_tenant_name_not_empty CHECK (LENGTH(TRIM(name)) > 0),
    CONSTRAINT chk_tenant_domain_not_empty CHECK (LENGTH(TRIM(domain)) > 0),
    CONSTRAINT chk_client_id_not_empty CHECK (LENGTH(TRIM(client_id)) > 0)
);

-- Create indexes for performance
CREATE INDEX idx_tenants_domain ON tenants(domain);
CREATE INDEX idx_tenants_client_id ON tenants(client_id);
CREATE INDEX idx_tenants_is_active ON tenants(is_active);
CREATE INDEX idx_tenants_created_at ON tenants(created_at);

-- =============================================================================
-- USER MANAGEMENT
-- =============================================================================

-- Users table with tenant isolation
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    username VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(500) NOT NULL, -- BCrypt hashed password
    
    -- Personal information
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    
    -- Account status
    is_active BOOLEAN DEFAULT true,
    is_tenant_admin BOOLEAN DEFAULT false, -- First user in tenant becomes admin
    email_verified BOOLEAN DEFAULT false,
    account_locked BOOLEAN DEFAULT false,
    password_expires_at TIMESTAMP,
    
    -- Invitation system
    invitation_token VARCHAR(255), -- For email invitation flow
    invitation_expires_at TIMESTAMP,
    invited_by UUID REFERENCES users(id),
    
    -- Login tracking
    last_login_at TIMESTAMP,
    failed_login_attempts INTEGER DEFAULT 0,
    last_failed_login_at TIMESTAMP,
    
    -- Audit fields
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Tenant-scoped uniqueness constraints
    CONSTRAINT uk_users_tenant_username UNIQUE(tenant_id, username),
    CONSTRAINT uk_users_tenant_email UNIQUE(tenant_id, email),
    
    -- Business logic constraints
    CONSTRAINT chk_username_not_empty CHECK (LENGTH(TRIM(username)) > 0),
    CONSTRAINT chk_email_format CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'),
    CONSTRAINT chk_password_hash_not_empty CHECK (LENGTH(TRIM(password_hash)) > 0)
);

-- Indexes for user queries
CREATE INDEX idx_users_tenant_id ON users(tenant_id);
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_is_active ON users(is_active);
CREATE INDEX idx_users_tenant_admin ON users(tenant_id, is_tenant_admin);
CREATE INDEX idx_users_invitation_token ON users(invitation_token) WHERE invitation_token IS NOT NULL;
CREATE INDEX idx_users_created_at ON users(created_at);

-- =============================================================================
-- ROLE-BASED ACCESS CONTROL
-- =============================================================================

-- Roles table supporting both tenant-specific and global roles
CREATE TABLE roles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL, -- TENANT_ADMIN, TENANT_USER, GLOBAL_ADMIN, etc.
    description TEXT,
    is_global BOOLEAN DEFAULT false, -- true for GLOBAL_ prefixed roles
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE, -- null for global roles
    
    -- JSON array of permissions
    permissions JSONB NOT NULL DEFAULT '[]'::jsonb,
    
    -- Role hierarchy and inheritance
    parent_role_id UUID REFERENCES roles(id),
    
    -- Status
    is_active BOOLEAN DEFAULT true,
    
    -- Audit fields
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CONSTRAINT uk_roles_name_tenant UNIQUE(name, tenant_id),
    CONSTRAINT chk_role_name_not_empty CHECK (LENGTH(TRIM(name)) > 0),
    CONSTRAINT chk_global_role_no_tenant CHECK (
        (is_global = true AND tenant_id IS NULL) OR 
        (is_global = false AND tenant_id IS NOT NULL)
    )
);

-- Indexes for role queries
CREATE INDEX idx_roles_tenant_id ON roles(tenant_id);
CREATE INDEX idx_roles_is_global ON roles(is_global);
CREATE INDEX idx_roles_name ON roles(name);
CREATE INDEX idx_roles_is_active ON roles(is_active);

-- =============================================================================
-- USER-ROLE ASSIGNMENTS
-- =============================================================================

-- User role assignments (many-to-many relationship)
CREATE TABLE user_roles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    
    -- Assignment metadata
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    assigned_by UUID REFERENCES users(id), -- Who assigned this role
    expires_at TIMESTAMP, -- Optional role expiration
    
    -- Status
    is_active BOOLEAN DEFAULT true,
    
    -- Ensure unique user-role combinations
    CONSTRAINT uk_user_roles_user_role UNIQUE(user_id, role_id)
);

-- Indexes for user role queries
CREATE INDEX idx_user_roles_user_id ON user_roles(user_id);
CREATE INDEX idx_user_roles_role_id ON user_roles(role_id);
CREATE INDEX idx_user_roles_assigned_at ON user_roles(assigned_at);
CREATE INDEX idx_user_roles_is_active ON user_roles(is_active);

-- =============================================================================
-- OAUTH2 AUTHORIZATION SERVER TABLES (Spring Security OAuth2)
-- =============================================================================

-- OAuth2 Authorization Consent (Spring Security requirement)
CREATE TABLE oauth2_authorization_consent (
    registered_client_id VARCHAR(100) NOT NULL,
    principal_name VARCHAR(200) NOT NULL,
    authorities VARCHAR(1000) NOT NULL,
    
    PRIMARY KEY (registered_client_id, principal_name)
);

-- OAuth2 Authorization (Spring Security requirement for storing authorization codes, access tokens, etc.)
CREATE TABLE oauth2_authorization (
    id VARCHAR(100) NOT NULL PRIMARY KEY,
    registered_client_id VARCHAR(100) NOT NULL,
    principal_name VARCHAR(200) NOT NULL,
    authorization_grant_type VARCHAR(100) NOT NULL,
    authorized_scopes VARCHAR(1000) DEFAULT NULL,
    attributes TEXT DEFAULT NULL,
    state VARCHAR(500) DEFAULT NULL,
    
    -- Authorization Code flow fields
    authorization_code_value TEXT DEFAULT NULL,
    authorization_code_issued_at TIMESTAMP DEFAULT NULL,
    authorization_code_expires_at TIMESTAMP DEFAULT NULL,
    authorization_code_metadata TEXT DEFAULT NULL,
    
    -- Access Token fields
    access_token_value TEXT DEFAULT NULL,
    access_token_issued_at TIMESTAMP DEFAULT NULL,
    access_token_expires_at TIMESTAMP DEFAULT NULL,
    access_token_metadata TEXT DEFAULT NULL,
    access_token_type VARCHAR(100) DEFAULT NULL,
    access_token_scopes VARCHAR(1000) DEFAULT NULL,
    
    -- OIDC ID Token fields
    oidc_id_token_value TEXT DEFAULT NULL,
    oidc_id_token_issued_at TIMESTAMP DEFAULT NULL,
    oidc_id_token_expires_at TIMESTAMP DEFAULT NULL,
    oidc_id_token_metadata TEXT DEFAULT NULL,
    
    -- Refresh Token fields
    refresh_token_value TEXT DEFAULT NULL,
    refresh_token_issued_at TIMESTAMP DEFAULT NULL,
    refresh_token_expires_at TIMESTAMP DEFAULT NULL,
    refresh_token_metadata TEXT DEFAULT NULL,
    
    -- Device Code flow fields (for future support)
    user_code_value TEXT DEFAULT NULL,
    user_code_issued_at TIMESTAMP DEFAULT NULL,
    user_code_expires_at TIMESTAMP DEFAULT NULL,
    user_code_metadata TEXT DEFAULT NULL,
    device_code_value TEXT DEFAULT NULL,
    device_code_issued_at TIMESTAMP DEFAULT NULL,
    device_code_expires_at TIMESTAMP DEFAULT NULL,
    device_code_metadata TEXT DEFAULT NULL
);

-- Indexes for OAuth2 authorization queries
CREATE INDEX idx_oauth2_authorization_client_id ON oauth2_authorization(registered_client_id);
CREATE INDEX idx_oauth2_authorization_principal ON oauth2_authorization(principal_name);
CREATE INDEX idx_oauth2_authorization_code ON oauth2_authorization(authorization_code_value) WHERE authorization_code_value IS NOT NULL;
CREATE INDEX idx_oauth2_authorization_access_token ON oauth2_authorization(access_token_value) WHERE access_token_value IS NOT NULL;
CREATE INDEX idx_oauth2_authorization_refresh_token ON oauth2_authorization(refresh_token_value) WHERE refresh_token_value IS NOT NULL;

-- =============================================================================
-- AUDIT AND LOGGING TABLES
-- =============================================================================

-- Audit log for tracking important security events
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    event_type VARCHAR(100) NOT NULL, -- LOGIN, LOGOUT, ROLE_ASSIGNED, etc.
    event_description TEXT,
    ip_address INET,
    user_agent TEXT,
    additional_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for audit queries
CREATE INDEX idx_audit_logs_tenant_id ON audit_logs(tenant_id);
CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_event_type ON audit_logs(event_type);
CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at);

-- =============================================================================
-- UPDATED_AT TRIGGERS
-- =============================================================================

-- Function to automatically update updated_at timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply updated_at triggers to relevant tables
CREATE TRIGGER update_tenants_updated_at 
    BEFORE UPDATE ON tenants 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_users_updated_at 
    BEFORE UPDATE ON users 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_roles_updated_at 
    BEFORE UPDATE ON roles 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- COMMENTS FOR DOCUMENTATION
-- =============================================================================

COMMENT ON TABLE tenants IS 'Organizations/companies using the multi-tenant OAuth2 system';
COMMENT ON COLUMN tenants.client_id IS 'OAuth2 client identifier, format: tenant_{id}_web';
COMMENT ON COLUMN tenants.callback_urls IS 'Array of allowed OAuth2 redirect URIs for this tenant';
COMMENT ON COLUMN tenants.api_key IS 'Legacy API key for WebSocket connections (to be deprecated)';

COMMENT ON TABLE users IS 'Users belonging to tenants, with tenant-scoped uniqueness';
COMMENT ON COLUMN users.is_tenant_admin IS 'Admin users can manage other users within their tenant';
COMMENT ON COLUMN users.invitation_token IS 'Secure token for email invitation flow';

COMMENT ON TABLE roles IS 'Roles supporting both tenant-specific (TENANT_*) and global (GLOBAL_*) permissions';
COMMENT ON COLUMN roles.permissions IS 'JSON array of permission strings like ["documents:read", "users:manage"]';

COMMENT ON TABLE user_roles IS 'Many-to-many assignment of roles to users with audit trail';

COMMENT ON TABLE oauth2_authorization IS 'Spring Security OAuth2 authorization storage for codes, tokens, and consent';

COMMENT ON TABLE audit_logs IS 'Security and operational audit trail for compliance';