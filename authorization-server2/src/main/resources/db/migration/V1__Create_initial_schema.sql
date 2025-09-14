-- =====================================================================================
-- Initial Schema Creation for Authorization Server
-- =====================================================================================

-- Create tenants table (organization information)
CREATE TABLE tenants (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name VARCHAR(255) NOT NULL,
    domain VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create roles table (global roles)
CREATE TABLE roles (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create users table
CREATE TABLE users (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    is_active BOOLEAN NOT NULL DEFAULT true,
    is_email_verified BOOLEAN NOT NULL DEFAULT false,
    last_login_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create user_roles junction table (many-to-many relationship)
CREATE TABLE user_roles (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id VARCHAR(36) NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, role_id)
);

-- Create registered_clients table for OAuth2 clients
CREATE TABLE registered_clients (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    client_id VARCHAR(255) UNIQUE NOT NULL,
    client_secret VARCHAR(500),
    client_name VARCHAR(255) NOT NULL,
    client_authentication_methods TEXT NOT NULL, -- JSON array
    authorization_grant_types TEXT NOT NULL, -- JSON array
    redirect_uris TEXT, -- JSON array
    post_logout_redirect_uris TEXT, -- JSON array
    scopes TEXT NOT NULL, -- JSON array
    client_settings TEXT, -- JSON object
    token_settings TEXT, -- JSON object
    require_authorization_consent BOOLEAN NOT NULL DEFAULT true,
    require_proof_key BOOLEAN NOT NULL DEFAULT false,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================================================
-- Create Indexes for Performance
-- =====================================================================================

-- Tenants indexes
CREATE INDEX idx_tenants_domain ON tenants(domain);
CREATE INDEX idx_tenants_is_active ON tenants(is_active);

-- Users indexes  
CREATE INDEX idx_users_tenant_id ON users(tenant_id);
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_is_active ON users(is_active);
CREATE INDEX idx_users_tenant_username ON users(tenant_id, username);

-- Roles indexes
CREATE INDEX idx_roles_name ON roles(name);
CREATE INDEX idx_roles_is_active ON roles(is_active);

-- User roles indexes
CREATE INDEX idx_user_roles_user_id ON user_roles(user_id);
CREATE INDEX idx_user_roles_role_id ON user_roles(role_id);

-- Registered clients indexes
CREATE INDEX idx_registered_clients_tenant_id ON registered_clients(tenant_id);
CREATE INDEX idx_registered_clients_client_id ON registered_clients(client_id);
CREATE INDEX idx_registered_clients_is_active ON registered_clients(is_active);

-- =====================================================================================
-- Insert Default Data
-- =====================================================================================

-- Insert default roles
INSERT INTO roles (id, name, description) VALUES
('550e8400-e29b-41d4-a716-446655440000', 'ADMIN', 'System administrator with full access'),
('550e8400-e29b-41d4-a716-446655440001', 'USER', 'Standard user with basic access'),
('550e8400-e29b-41d4-a716-446655440002', 'TENANT_ADMIN', 'Tenant administrator with tenant-level access');

-- Insert default tenant
INSERT INTO tenants (id, name, domain, description) VALUES
('550e8400-e29b-41d4-a716-446655440010', 'System', 'system.local', 'Default system tenant');

-- Insert default admin user (password: admin123)
INSERT INTO users (id, tenant_id, username, email, password, first_name, last_name, is_active, is_email_verified) VALUES
('550e8400-e29b-41d4-a716-446655440020', '550e8400-e29b-41d4-a716-446655440010', 'admin', 'admin@system.local', '{noop}admin123', 'System', 'Administrator', true, true);

-- Insert default user (password: user123)
INSERT INTO users (id, tenant_id, username, email, password, first_name, last_name, is_active, is_email_verified) VALUES
('550e8400-e29b-41d4-a716-446655440021', '550e8400-e29b-41d4-a716-446655440010', 'user', 'user@system.local', '{noop}user123', 'Default', 'User', true, true);

-- Assign roles to users
INSERT INTO user_roles (user_id, role_id) VALUES
('550e8400-e29b-41d4-a716-446655440020', '550e8400-e29b-41d4-a716-446655440000'), -- admin -> ADMIN
('550e8400-e29b-41d4-a716-446655440020', '550e8400-e29b-41d4-a716-446655440002'), -- admin -> TENANT_ADMIN
('550e8400-e29b-41d4-a716-446655440021', '550e8400-e29b-41d4-a716-446655440001'); -- user -> USER

-- Insert default registered client
INSERT INTO registered_clients (id, tenant_id, client_id, client_secret, client_name, client_authentication_methods, authorization_grant_types, redirect_uris, post_logout_redirect_uris, scopes, client_settings, token_settings, require_authorization_consent, require_proof_key) VALUES
('550e8400-e29b-41d4-a716-446655440030', '550e8400-e29b-41d4-a716-446655440010', 'webclient', '{noop}webclient-secret', 'Web Client', '["client_secret_basic", "client_secret_post"]', '["authorization_code", "refresh_token"]', '["http://localhost:4200/callback"]', '["http://localhost:4200"]', '["openid", "profile", "read", "write"]', '{}', '{"accessTokenTimeToLive": "PT1H", "refreshTokenTimeToLive": "P30D"}', false, false);