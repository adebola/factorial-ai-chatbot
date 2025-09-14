-- V6: Add tenant settings table for branding and chat widget customization

CREATE TABLE tenant_settings (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL,
    
    -- Company branding colors
    primary_color VARCHAR(7), -- Hex color code #RRGGBB
    secondary_color VARCHAR(7), -- Hex color code #RRGGBB
    
    -- Chat widget text customization
    hover_text VARCHAR(255) DEFAULT 'Chat with us!',
    welcome_message TEXT DEFAULT 'Hello! How can I help you today?',
    chat_window_title VARCHAR(100) DEFAULT 'Chat Support',
    
    -- Future extensibility
    additional_settings JSON DEFAULT '{}',
    
    -- Status
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE,
    
    -- Constraints
    CONSTRAINT fk_tenant_settings_tenant FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE,
    CONSTRAINT uk_tenant_settings_tenant_id UNIQUE (tenant_id),
    
    -- Validate hex color format
    CONSTRAINT chk_primary_color CHECK (primary_color IS NULL OR primary_color ~ '^#[0-9A-Fa-f]{6}$'),
    CONSTRAINT chk_secondary_color CHECK (secondary_color IS NULL OR secondary_color ~ '^#[0-9A-Fa-f]{6}$')
);

-- Create indexes for performance
CREATE INDEX idx_tenant_settings_tenant_id ON tenant_settings (tenant_id);
CREATE INDEX idx_tenant_settings_active ON tenant_settings (is_active);

-- Add comments for documentation
COMMENT ON TABLE tenant_settings IS 'Tenant-specific settings for chat widget and branding customization';
COMMENT ON COLUMN tenant_settings.primary_color IS 'Primary brand color in hex format (#RRGGBB)';
COMMENT ON COLUMN tenant_settings.secondary_color IS 'Secondary brand color in hex format (#RRGGBB)';
COMMENT ON COLUMN tenant_settings.hover_text IS 'Text shown when hovering over chat widget';
COMMENT ON COLUMN tenant_settings.welcome_message IS 'Initial message shown in chat window';
COMMENT ON COLUMN tenant_settings.chat_window_title IS 'Title displayed in chat window header';
COMMENT ON COLUMN tenant_settings.additional_settings IS 'JSON field for future extensibility without schema changes';