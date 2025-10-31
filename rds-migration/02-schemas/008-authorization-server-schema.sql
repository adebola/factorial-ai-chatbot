-- =====================================================
-- RDS MIGRATION SCRIPT: Authorization Server Schema
-- =====================================================
-- Database: authorization_db
-- Purpose: Create authorization server schema (Spring Boot + Flyway)
-- Dependencies: 01-initialization/001-create-databases-and-extensions.sql
-- Note: This consolidates all Flyway migrations (V1-V9) from authorization-server
-- =====================================================

\c authorization_db

-- =====================================================
-- CONSOLIDATED FLYWAY MIGRATIONS (V1-V9)
-- =====================================================
-- This script consolidates all Flyway migrations from the authorization-server
-- Original migrations: src/main/resources/db/migration/V1__through__V9
-- Last migration: V9__Add_subscription_id_to_tenants.sql
-- =====================================================

-- =====================================================
-- V1: INITIAL SCHEMA CREATION
-- =====================================================

-- Tenants Table (Organization information)
CREATE TABLE IF NOT EXISTS tenants (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    name VARCHAR(255) NOT NULL,
    domain VARCHAR(255) NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Roles Table (Global system roles)
CREATE TABLE IF NOT EXISTS roles (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Users Table
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    tenant_id VARCHAR(36) NOT NULL,
    username VARCHAR(100) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    is_active BOOLEAN NOT NULL DEFAULT true,
    is_email_verified BOOLEAN NOT NULL DEFAULT false,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_users_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
);

-- User Roles Junction Table (Many-to-many)
CREATE TABLE IF NOT EXISTS user_roles (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    user_id VARCHAR(36) NOT NULL,
    role_id VARCHAR(36) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_user_roles_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_user_roles_role FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
    CONSTRAINT uk_user_roles UNIQUE (user_id, role_id)
);

-- OAuth2 Registered Clients Table
CREATE TABLE IF NOT EXISTS registered_clients (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    client_id VARCHAR(255) NOT NULL UNIQUE,
    client_secret VARCHAR(500),
    client_name VARCHAR(255) NOT NULL,
    client_authentication_methods TEXT NOT NULL,
    authorization_grant_types TEXT NOT NULL,
    redirect_uris TEXT,
    post_logout_redirect_uris TEXT,
    scopes TEXT NOT NULL,
    client_settings TEXT,
    token_settings TEXT,
    require_authorization_consent BOOLEAN NOT NULL DEFAULT true,
    require_proof_key BOOLEAN NOT NULL DEFAULT false,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =====================================================
-- V3: ENHANCE TENANT MODEL
-- =====================================================

-- Add OAuth2 and billing fields to tenants
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS api_key VARCHAR(255) UNIQUE;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS config TEXT;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS plan_id VARCHAR(36);

-- =====================================================
-- V6: ADD TENANT SETTINGS TABLE
-- =====================================================

-- Tenant Settings Table (Branding and customization)
CREATE TABLE IF NOT EXISTS tenant_settings (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    tenant_id VARCHAR(36) NOT NULL UNIQUE,
    primary_color VARCHAR(7),
    secondary_color VARCHAR(7),
    hover_text VARCHAR(255) DEFAULT 'Chat with us!',
    welcome_message TEXT DEFAULT 'Hello! How can I help you today?',
    chat_window_title VARCHAR(100) DEFAULT 'Chat Support',
    additional_settings JSONB DEFAULT '{}',
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_tenant_settings_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
    CONSTRAINT chk_primary_color CHECK (primary_color IS NULL OR primary_color ~ '^#[0-9A-Fa-f]{6}$'),
    CONSTRAINT chk_secondary_color CHECK (secondary_color IS NULL OR secondary_color ~ '^#[0-9A-Fa-f]{6}$')
);

-- =====================================================
-- V7: ADD LOGO URL TO TENANT SETTINGS
-- =====================================================

ALTER TABLE tenant_settings ADD COLUMN IF NOT EXISTS company_logo_url VARCHAR(500);

-- =====================================================
-- V8: CREATE VERIFICATION TOKENS TABLE
-- =====================================================

-- Verification Tokens Table (Email verification, password reset)
CREATE TABLE IF NOT EXISTS verification_tokens (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    token VARCHAR(255) NOT NULL UNIQUE,
    user_id VARCHAR(36) NOT NULL,
    email VARCHAR(255) NOT NULL,
    token_type VARCHAR(50) NOT NULL DEFAULT 'EMAIL_VERIFICATION',
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_verification_tokens_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- =====================================================
-- V9: ADD SUBSCRIPTION ID TO TENANTS
-- =====================================================

ALTER TABLE tenants ADD COLUMN IF NOT EXISTS subscription_id VARCHAR(36);

-- =====================================================
-- CREATE INDEXES
-- =====================================================

-- Tenants indexes
CREATE INDEX IF NOT EXISTS idx_tenants_domain ON tenants(domain);
CREATE INDEX IF NOT EXISTS idx_tenants_is_active ON tenants(is_active);
CREATE INDEX IF NOT EXISTS idx_tenants_api_key ON tenants(api_key);
CREATE INDEX IF NOT EXISTS idx_tenants_subscription_id ON tenants(subscription_id);

-- Users indexes
CREATE INDEX IF NOT EXISTS idx_users_tenant_id ON users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active);
CREATE INDEX IF NOT EXISTS idx_users_tenant_username ON users(tenant_id, username);
CREATE INDEX IF NOT EXISTS idx_users_is_email_verified ON users(is_email_verified);

-- Roles indexes
CREATE INDEX IF NOT EXISTS idx_roles_name ON roles(name);
CREATE INDEX IF NOT EXISTS idx_roles_is_active ON roles(is_active);

-- User roles indexes
CREATE INDEX IF NOT EXISTS idx_user_roles_user_id ON user_roles(user_id);
CREATE INDEX IF NOT EXISTS idx_user_roles_role_id ON user_roles(role_id);

-- Registered clients indexes
CREATE INDEX IF NOT EXISTS idx_registered_clients_client_id ON registered_clients(client_id);
CREATE INDEX IF NOT EXISTS idx_registered_clients_is_active ON registered_clients(is_active);

-- Tenant settings indexes
CREATE INDEX IF NOT EXISTS idx_tenant_settings_tenant_id ON tenant_settings(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tenant_settings_active ON tenant_settings(is_active);
CREATE INDEX IF NOT EXISTS idx_tenant_settings_logo_url ON tenant_settings(company_logo_url);

-- Verification tokens indexes
CREATE INDEX IF NOT EXISTS idx_verification_tokens_token ON verification_tokens(token);
CREATE INDEX IF NOT EXISTS idx_verification_tokens_user_id ON verification_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_verification_tokens_email ON verification_tokens(email);
CREATE INDEX IF NOT EXISTS idx_verification_tokens_expires_at ON verification_tokens(expires_at);
CREATE INDEX IF NOT EXISTS idx_verification_tokens_token_type ON verification_tokens(token_type);
CREATE UNIQUE INDEX IF NOT EXISTS idx_verification_tokens_token_user_type
    ON verification_tokens(token, user_id, token_type);

-- =====================================================
-- CREATE UPDATE TRIGGER
-- =====================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for all tables with updated_at
CREATE TRIGGER update_tenants_updated_at
    BEFORE UPDATE ON tenants
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_roles_updated_at
    BEFORE UPDATE ON roles
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_registered_clients_updated_at
    BEFORE UPDATE ON registered_clients
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_tenant_settings_updated_at
    BEFORE UPDATE ON tenant_settings
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_verification_tokens_updated_at
    BEFORE UPDATE ON verification_tokens
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =====================================================
-- SEED DEFAULT DATA
-- =====================================================

-- Insert default roles
INSERT INTO roles (id, name, description) VALUES
('550e8400-e29b-41d4-a716-446655440000', 'ADMIN', 'System administrator with full access'),
('550e8400-e29b-41d4-a716-446655440001', 'USER', 'Standard user with basic access'),
('550e8400-e29b-41d4-a716-446655440002', 'TENANT_ADMIN', 'Tenant administrator with tenant-level access')
ON CONFLICT (id) DO NOTHING;

-- Insert default system tenant
INSERT INTO tenants (id, name, domain) VALUES
('550e8400-e29b-41d4-a716-446655440010', 'System', 'system.local')
ON CONFLICT (id) DO NOTHING;

-- Insert default admin user (password: admin123 with {noop} prefix for plain text in dev)
INSERT INTO users (id, tenant_id, username, email, password, first_name, last_name, is_active, is_email_verified) VALUES
('550e8400-e29b-41d4-a716-446655440020', '550e8400-e29b-41d4-a716-446655440010', 'admin', 'admin@system.local', '{noop}admin123', 'System', 'Administrator', true, true)
ON CONFLICT (id) DO NOTHING;

-- Insert default user (password: user123)
INSERT INTO users (id, tenant_id, username, email, password, first_name, last_name, is_active, is_email_verified) VALUES
('550e8400-e29b-41d4-a716-446655440021', '550e8400-e29b-41d4-a716-446655440010', 'user', 'user@system.local', '{noop}user123', 'Default', 'User', true, true)
ON CONFLICT (id) DO NOTHING;

-- Assign roles to users
INSERT INTO user_roles (user_id, role_id) VALUES
('550e8400-e29b-41d4-a716-446655440020', '550e8400-e29b-41d4-a716-446655440000'), -- admin -> ADMIN
('550e8400-e29b-41d4-a716-446655440020', '550e8400-e29b-41d4-a716-446655440002'), -- admin -> TENANT_ADMIN
('550e8400-e29b-41d4-a716-446655440021', '550e8400-e29b-41d4-a716-446655440001')  -- user -> USER
ON CONFLICT (user_id, role_id) DO NOTHING;

-- Insert default OAuth2 client (single client architecture)
-- Note: This uses BCrypt hashed password. For production, regenerate with proper BCrypt hash
INSERT INTO registered_clients (
    id,
    client_id,
    client_secret,
    client_name,
    client_authentication_methods,
    authorization_grant_types,
    redirect_uris,
    post_logout_redirect_uris,
    scopes,
    client_settings,
    token_settings,
    require_authorization_consent,
    require_proof_key,
    is_active
) VALUES (
    'default-webclient-id',
    'webclient',
    '{bcrypt}$2a$10$5oKw8aKs8bE8Ux8rKVJ5kuOKKe5XQzJJ5r1t5VkL9D8Z8gU5pKx4W',
    'Default Web Client',
    'client_secret_basic,client_secret_post',
    'authorization_code,refresh_token,client_credentials',
    'http://localhost:4200/callback,https://your-domain.com/callback',
    'http://localhost:4200/logout,https://your-domain.com/logout',
    'openid,profile,read,write',
    '{"requireAuthorizationConsent":false,"requireProofKey":true}',
    '{"accessTokenTimeToLive":"PT1H","refreshTokenTimeToLive":"P30D"}',
    false,
    true,
    true
) ON CONFLICT (client_id) DO NOTHING;

-- =====================================================
-- ADD TABLE COMMENTS
-- =====================================================

COMMENT ON TABLE tenants IS 'Organization/tenant information with OAuth2 and billing integration';
COMMENT ON TABLE roles IS 'Global system roles for RBAC';
COMMENT ON TABLE users IS 'User accounts with tenant isolation and email verification';
COMMENT ON TABLE user_roles IS 'Many-to-many relationship between users and roles';
COMMENT ON TABLE registered_clients IS 'OAuth2 registered clients - single client architecture';
COMMENT ON TABLE tenant_settings IS 'Tenant-specific branding and chat widget customization';
COMMENT ON TABLE verification_tokens IS 'Email verification and password reset tokens';

COMMENT ON COLUMN tenants.api_key IS 'Tenant-specific API key for service authentication';
COMMENT ON COLUMN tenants.config IS 'JSON configuration for tenant-specific settings';
COMMENT ON COLUMN tenants.plan_id IS 'References plan in billing_db';
COMMENT ON COLUMN tenants.subscription_id IS 'References subscription in onboard_db/billing_db';

COMMENT ON COLUMN tenant_settings.primary_color IS 'Primary brand color in hex format (#RRGGBB)';
COMMENT ON COLUMN tenant_settings.secondary_color IS 'Secondary brand color in hex format (#RRGGBB)';
COMMENT ON COLUMN tenant_settings.hover_text IS 'Text shown when hovering over chat widget';
COMMENT ON COLUMN tenant_settings.welcome_message IS 'Initial message shown in chat window';
COMMENT ON COLUMN tenant_settings.chat_window_title IS 'Title displayed in chat window header';
COMMENT ON COLUMN tenant_settings.company_logo_url IS 'URL of company logo for branding';
COMMENT ON COLUMN tenant_settings.additional_settings IS 'JSON field for future extensibility';

COMMENT ON COLUMN verification_tokens.token_type IS 'EMAIL_VERIFICATION, PASSWORD_RESET, etc.';

-- =====================================================
-- GRANT PERMISSIONS
-- =====================================================

-- Replace 'app_user' with your actual RDS application username
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;

-- =====================================================
-- VERIFICATION QUERIES
-- =====================================================

-- Verify tables created
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN (
    'tenants', 'roles', 'users', 'user_roles',
    'registered_clients', 'tenant_settings', 'verification_tokens'
  )
ORDER BY table_name;

-- Verify default data seeded
SELECT COUNT(*) as role_count FROM roles;
SELECT COUNT(*) as tenant_count FROM tenants;
SELECT COUNT(*) as user_count FROM users;
SELECT COUNT(*) as client_count FROM registered_clients;

-- List default roles
SELECT name, description FROM roles ORDER BY name;

-- List default users and their roles
SELECT
    u.username,
    u.email,
    u.first_name,
    u.last_name,
    STRING_AGG(r.name, ', ') as roles
FROM users u
JOIN user_roles ur ON u.id = ur.user_id
JOIN roles r ON ur.role_id = r.id
GROUP BY u.id, u.username, u.email, u.first_name, u.last_name
ORDER BY u.username;

-- =====================================================
-- FLYWAY COMPATIBILITY
-- =====================================================

-- Create Flyway schema history table
-- This ensures compatibility if you later run Flyway migrations
CREATE TABLE IF NOT EXISTS flyway_schema_history (
    installed_rank INT NOT NULL PRIMARY KEY,
    version VARCHAR(50),
    description VARCHAR(200) NOT NULL,
    type VARCHAR(20) NOT NULL,
    script VARCHAR(1000) NOT NULL,
    checksum INT,
    installed_by VARCHAR(100) NOT NULL,
    installed_on TIMESTAMP NOT NULL DEFAULT now(),
    execution_time INT NOT NULL,
    success BOOLEAN NOT NULL
);

-- Mark this consolidation as baseline
INSERT INTO flyway_schema_history (
    installed_rank, version, description, type, script,
    checksum, installed_by, execution_time, success
) VALUES (
    1, '9', 'Consolidated RDS migration V1-V9', 'SQL',
    '008-authorization-server-schema.sql',
    0, 'rds-migration', 0, true
) ON CONFLICT (installed_rank) DO NOTHING;

-- =====================================================
-- NOTES FOR RDS DEPLOYMENT
-- =====================================================

/*
1. FLYWAY INTEGRATION:
   - This script consolidates Flyway migrations V1-V9
   - Spring Boot will see flyway_schema_history and skip re-running migrations
   - New migrations (V10+) will run normally via Spring Boot

2. DEFAULT CREDENTIALS:
   - Admin: admin@system.local / admin123
   - User: user@system.local / user123
   - IMPORTANT: Change these in production!

3. OAUTH2 CLIENT:
   - Single client architecture (not per-tenant)
   - Client ID: webclient
   - Client secret is BCrypt hashed
   - Supports authorization_code, refresh_token, client_credentials flows

4. MULTI-TENANCY:
   - Users belong to tenants via tenant_id foreign key
   - Tenant settings allow per-tenant branding
   - API keys for tenant-specific service authentication

5. EMAIL VERIFICATION:
   - verification_tokens table supports email verification flow
   - Tokens have expiration (expires_at)
   - Token types: EMAIL_VERIFICATION, PASSWORD_RESET

6. PRODUCTION SETUP:
   - Update default user passwords
   - Regenerate OAuth2 client secret with proper BCrypt
   - Configure redirect_uris for production domain
   - Set up proper tenant settings with branding

7. SPRING BOOT CONFIGURATION:
   Update application.yml with RDS connection:

   spring:
     datasource:
       url: jdbc:postgresql://your-rds-endpoint:5432/authorization_db
       username: postgres
       password: your-secure-password
     flyway:
       baseline-on-migrate: true
       baseline-version: 9

8. SUBSCRIPTION INTEGRATION:
   - tenants.subscription_id references onboard_db.subscriptions
   - Cross-database foreign keys not enforced at DB level
   - Application layer must maintain referential integrity
*/