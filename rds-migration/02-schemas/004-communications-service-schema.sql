-- =====================================================
-- RDS MIGRATION SCRIPT: Communications Service Schema
-- =====================================================
-- Database: communications_db
-- Purpose: Create communications service schema for email/SMS delivery
-- Dependencies: 01-initialization/001-create-databases-and-extensions.sql
-- Note: This script will be supplemented by Alembic migrations
-- =====================================================

\c communications_db

-- =====================================================
-- CREATE ENUM TYPES
-- =====================================================

DO $$ BEGIN
    CREATE TYPE message_status AS ENUM ('pending', 'sent', 'delivered', 'failed', 'bounced', 'opened', 'clicked');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE template_type AS ENUM ('email', 'sms');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- =====================================================
-- CREATE TABLES
-- =====================================================

-- Email Messages Table
CREATE TABLE IF NOT EXISTS email_messages (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    tenant_id VARCHAR(36) NOT NULL,
    to_email VARCHAR(255) NOT NULL,
    to_name VARCHAR(255),
    from_email VARCHAR(255) NOT NULL,
    from_name VARCHAR(255),
    subject VARCHAR(500) NOT NULL,
    html_content TEXT,
    text_content TEXT,
    status message_status DEFAULT 'pending',
    provider_message_id VARCHAR(255),
    attachments JSONB,
    sent_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    opened_at TIMESTAMPTZ,
    clicked_at TIMESTAMPTZ,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    last_retry_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- SMS Messages Table
CREATE TABLE IF NOT EXISTS sms_messages (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    tenant_id VARCHAR(36) NOT NULL,
    to_phone VARCHAR(20) NOT NULL,
    from_phone VARCHAR(20),
    message TEXT NOT NULL,
    status message_status DEFAULT 'pending',
    provider_message_id VARCHAR(255),
    sent_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    last_retry_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Message Templates Table
CREATE TABLE IF NOT EXISTS message_templates (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    tenant_id VARCHAR(36) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    template_type template_type NOT NULL,
    subject_template VARCHAR(500),
    html_template TEXT,
    text_template TEXT,
    variables JSONB,
    is_active BOOLEAN DEFAULT true,
    usage_count INTEGER DEFAULT 0,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Delivery Logs Table
CREATE TABLE IF NOT EXISTS delivery_logs (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    message_id VARCHAR(36) NOT NULL,
    message_type template_type NOT NULL,
    tenant_id VARCHAR(36) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    event_data JSONB,
    provider_name VARCHAR(50),
    provider_response JSONB,
    occurred_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Tenant Settings Table
CREATE TABLE IF NOT EXISTS tenant_settings (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    tenant_id VARCHAR(36) NOT NULL UNIQUE,
    default_from_email VARCHAR(255),
    default_from_name VARCHAR(255),
    email_signature TEXT,
    default_from_phone VARCHAR(20),
    daily_email_limit INTEGER DEFAULT 1000,
    daily_sms_limit INTEGER DEFAULT 500,
    emails_sent_today INTEGER DEFAULT 0,
    sms_sent_today INTEGER DEFAULT 0,
    limit_reset_date TIMESTAMPTZ DEFAULT now(),
    enable_open_tracking BOOLEAN DEFAULT true,
    enable_click_tracking BOOLEAN DEFAULT true,
    enable_unsubscribe_link BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =====================================================
-- CREATE INDEXES
-- =====================================================

-- Email messages indexes
CREATE INDEX IF NOT EXISTS idx_email_tenant_id ON email_messages(tenant_id);
CREATE INDEX IF NOT EXISTS idx_email_status ON email_messages(status);
CREATE INDEX IF NOT EXISTS idx_email_created_at ON email_messages(created_at);
CREATE INDEX IF NOT EXISTS idx_email_provider_message_id ON email_messages(provider_message_id);
CREATE INDEX IF NOT EXISTS idx_email_to_email ON email_messages(to_email);

-- SMS messages indexes
CREATE INDEX IF NOT EXISTS idx_sms_tenant_id ON sms_messages(tenant_id);
CREATE INDEX IF NOT EXISTS idx_sms_status ON sms_messages(status);
CREATE INDEX IF NOT EXISTS idx_sms_created_at ON sms_messages(created_at);
CREATE INDEX IF NOT EXISTS idx_sms_provider_message_id ON sms_messages(provider_message_id);
CREATE INDEX IF NOT EXISTS idx_sms_to_phone ON sms_messages(to_phone);

-- Message templates indexes
CREATE INDEX IF NOT EXISTS idx_template_tenant_id ON message_templates(tenant_id);
CREATE INDEX IF NOT EXISTS idx_template_type ON message_templates(template_type);
CREATE INDEX IF NOT EXISTS idx_template_active ON message_templates(is_active);
CREATE INDEX IF NOT EXISTS idx_template_name ON message_templates(name);

-- Delivery logs indexes
CREATE INDEX IF NOT EXISTS idx_delivery_message_id ON delivery_logs(message_id);
CREATE INDEX IF NOT EXISTS idx_delivery_event_type ON delivery_logs(event_type);
CREATE INDEX IF NOT EXISTS idx_delivery_timestamp ON delivery_logs(occurred_at);
CREATE INDEX IF NOT EXISTS idx_delivery_tenant_id ON delivery_logs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_delivery_message_type ON delivery_logs(message_type);

-- Tenant settings indexes
CREATE INDEX IF NOT EXISTS idx_tenant_settings_tenant_id ON tenant_settings(tenant_id);

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

-- Trigger for email_messages
CREATE TRIGGER update_email_messages_updated_at
    BEFORE UPDATE ON email_messages
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Trigger for sms_messages
CREATE TRIGGER update_sms_messages_updated_at
    BEFORE UPDATE ON sms_messages
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Trigger for message_templates
CREATE TRIGGER update_message_templates_updated_at
    BEFORE UPDATE ON message_templates
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Trigger for tenant_settings
CREATE TRIGGER update_tenant_settings_updated_at
    BEFORE UPDATE ON tenant_settings
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =====================================================
-- VERIFICATION QUERIES
-- =====================================================

-- Verify tables created
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN ('email_messages', 'sms_messages', 'message_templates', 'delivery_logs', 'tenant_settings')
ORDER BY table_name;

-- Verify indexes created
SELECT tablename, indexname FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN ('email_messages', 'sms_messages', 'message_templates', 'delivery_logs', 'tenant_settings')
ORDER BY tablename, indexname;

-- =====================================================
-- NOTES
-- =====================================================

/*
1. EMAIL/SMS DELIVERY:
   - Messages are queued with status 'pending'
   - External workers (Celery/APScheduler) send messages
   - Delivery logs track all webhook events from providers
   - Retry logic handles temporary failures

2. RATE LIMITING:
   - tenant_settings stores daily limits
   - Counters reset at limit_reset_date
   - Implement daily reset job using pg_cron or external scheduler

3. TEMPLATES:
   - Templates use Jinja2 syntax for variable substitution
   - variables JSONB stores list of required variables
   - usage_count tracks template popularity

4. MONITORING:
   - Track delivery rates: SELECT status, COUNT(*) FROM email_messages GROUP BY status
   - Failed messages: SELECT * FROM email_messages WHERE status = 'failed' AND retry_count < 3
   - Daily volume: SELECT DATE(created_at), COUNT(*) FROM email_messages GROUP BY DATE(created_at)

5. CLEANUP:
   - Archive messages older than 90 days
   - Delete delivery_logs older than 30 days
   - Keep templates indefinitely (soft delete if needed)
*/