-- =====================================================
-- RDS MIGRATION SCRIPT: Onboarding Service Schema
-- =====================================================
-- Database: onboard_db
-- Purpose: Create onboarding service schema for tenants, documents, subscriptions
-- Dependencies: 01-initialization/001-create-databases-and-extensions.sql
-- Note: This script will be supplemented by Alembic migrations
-- =====================================================

\c onboard_db

-- =====================================================
-- CREATE ENUM TYPES
-- =====================================================

DO $$ BEGIN
    CREATE TYPE document_status AS ENUM ('pending', 'processing', 'completed', 'failed');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE website_ingestion_status AS ENUM ('pending', 'in_progress', 'completed', 'failed');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE subscription_status AS ENUM ('active', 'pending', 'past_due', 'cancelled', 'expired', 'trialing');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE billing_cycle AS ENUM ('monthly', 'yearly');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE payment_status AS ENUM ('pending', 'processing', 'completed', 'failed', 'cancelled', 'refunded');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE payment_method_type AS ENUM ('card', 'bank_transfer', 'ussd', 'qr', 'mobile_money');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE transaction_type AS ENUM ('subscription', 'upgrade', 'downgrade', 'renewal', 'refund');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- =====================================================
-- CORE TABLES (Base schema - will be extended by Alembic)
-- =====================================================

-- Documents Table
CREATE TABLE IF NOT EXISTS documents (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    tenant_id VARCHAR(36) NOT NULL,
    filename VARCHAR(500),
    original_filename VARCHAR(500),
    file_path VARCHAR(1000),
    file_size INTEGER,
    mime_type VARCHAR(100),
    status document_status DEFAULT 'pending',
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ
);

-- Website Ingestions Table
CREATE TABLE IF NOT EXISTS website_ingestions (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    tenant_id VARCHAR(36) NOT NULL,
    base_url VARCHAR(500),
    status website_ingestion_status DEFAULT 'pending',
    pages_discovered INTEGER DEFAULT 0,
    pages_processed INTEGER DEFAULT 0,
    pages_failed INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Website Pages Table
CREATE TABLE IF NOT EXISTS website_pages (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    tenant_id VARCHAR(36) NOT NULL,
    ingestion_id VARCHAR(36) NOT NULL,
    url VARCHAR(1000),
    title VARCHAR(500),
    content_hash VARCHAR(64),
    status document_status DEFAULT 'pending',
    error_message TEXT,
    scraped_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Document Categories Table
CREATE TABLE IF NOT EXISTS document_categories (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    tenant_id VARCHAR(36) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    parent_category_id VARCHAR(36),
    color VARCHAR(7),
    icon VARCHAR(50),
    is_system_category BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_parent_category FOREIGN KEY (parent_category_id)
        REFERENCES document_categories(id) ON DELETE SET NULL,
    CONSTRAINT unique_category_per_tenant UNIQUE (tenant_id, name, parent_category_id)
);

-- Document Tags Table
CREATE TABLE IF NOT EXISTS document_tags (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    tenant_id VARCHAR(36) NOT NULL,
    name VARCHAR(100) NOT NULL,
    tag_type VARCHAR(50) DEFAULT 'custom',
    usage_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT unique_tag_per_tenant UNIQUE (tenant_id, name)
);

-- Document Category Assignments Table
CREATE TABLE IF NOT EXISTS document_category_assignments (
    document_id VARCHAR(36) NOT NULL,
    category_id VARCHAR(36) NOT NULL,
    confidence_score FLOAT,
    assigned_by VARCHAR(20) DEFAULT 'user',
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (document_id, category_id),
    CONSTRAINT fk_document FOREIGN KEY (document_id)
        REFERENCES documents(id) ON DELETE CASCADE,
    CONSTRAINT fk_category FOREIGN KEY (category_id)
        REFERENCES document_categories(id) ON DELETE CASCADE
);

-- Document Tag Assignments Table
CREATE TABLE IF NOT EXISTS document_tag_assignments (
    document_id VARCHAR(36) NOT NULL,
    tag_id VARCHAR(36) NOT NULL,
    confidence_score FLOAT,
    assigned_by VARCHAR(20) DEFAULT 'user',
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (document_id, tag_id),
    CONSTRAINT fk_document_tag FOREIGN KEY (document_id)
        REFERENCES documents(id) ON DELETE CASCADE,
    CONSTRAINT fk_tag FOREIGN KEY (tag_id)
        REFERENCES document_tags(id) ON DELETE CASCADE
);

-- =====================================================
-- SUBSCRIPTION & BILLING TABLES
-- =====================================================

-- Plans Table (Legacy - now in billing_db, but kept for backward compatibility)
CREATE TABLE IF NOT EXISTS plans (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    document_limit INTEGER,
    website_limit INTEGER,
    daily_chat_limit INTEGER,
    monthly_chat_limit INTEGER,
    monthly_plan_cost NUMERIC(10, 2),
    yearly_plan_cost NUMERIC(10, 2),
    features JSONB,
    is_active BOOLEAN DEFAULT true,
    is_deleted BOOLEAN DEFAULT false,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Subscriptions Table
CREATE TABLE IF NOT EXISTS subscriptions (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    tenant_id VARCHAR(36) NOT NULL,
    plan_id VARCHAR(36),
    status subscription_status DEFAULT 'pending',
    billing_cycle billing_cycle DEFAULT 'monthly',
    amount NUMERIC(10, 2),
    currency VARCHAR(3) DEFAULT 'NGN',
    starts_at TIMESTAMPTZ,
    ends_at TIMESTAMPTZ,
    current_period_start TIMESTAMPTZ,
    current_period_end TIMESTAMPTZ,
    trial_starts_at TIMESTAMPTZ,
    trial_ends_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    cancellation_reason TEXT,
    cancel_at_period_end BOOLEAN DEFAULT false,
    pending_plan_id VARCHAR(36),
    pending_billing_cycle billing_cycle,
    pending_plan_effective_date TIMESTAMPTZ,
    grace_period_ends_at TIMESTAMPTZ,
    auto_renew BOOLEAN DEFAULT true,
    subscription_metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_plan FOREIGN KEY (plan_id) REFERENCES plans(id)
);

-- Payments Table
CREATE TABLE IF NOT EXISTS payments (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    subscription_id VARCHAR(36),
    tenant_id VARCHAR(36) NOT NULL,
    amount NUMERIC(10, 2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'NGN',
    status payment_status DEFAULT 'pending',
    payment_method payment_method_type,
    transaction_type transaction_type,
    paystack_reference VARCHAR(255) UNIQUE,
    paystack_access_code VARCHAR(255),
    paystack_transaction_id VARCHAR(255),
    gateway_response JSONB,
    processed_at TIMESTAMPTZ,
    description TEXT,
    payment_metadata JSONB,
    refunded_amount NUMERIC(10, 2),
    refund_reason TEXT,
    refunded_at TIMESTAMPTZ,
    failure_reason TEXT,
    failure_code VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_subscription FOREIGN KEY (subscription_id)
        REFERENCES subscriptions(id)
);

-- Payment Methods Table
CREATE TABLE IF NOT EXISTS payment_methods (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    tenant_id VARCHAR(36) NOT NULL,
    type payment_method_type NOT NULL,
    is_default BOOLEAN DEFAULT false,
    is_active BOOLEAN DEFAULT true,
    card_last_four VARCHAR(4),
    card_brand VARCHAR(20),
    card_exp_month INTEGER,
    card_exp_year INTEGER,
    bank_name VARCHAR(100),
    account_name VARCHAR(255),
    paystack_authorization_code VARCHAR(255),
    paystack_customer_code VARCHAR(255),
    payment_method_metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Invoices Table
CREATE TABLE IF NOT EXISTS invoices (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    subscription_id VARCHAR(36),
    tenant_id VARCHAR(36) NOT NULL,
    invoice_number VARCHAR(50) NOT NULL UNIQUE,
    status payment_status DEFAULT 'pending',
    subtotal NUMERIC(10, 2),
    tax_amount NUMERIC(10, 2),
    total_amount NUMERIC(10, 2),
    currency VARCHAR(3) DEFAULT 'NGN',
    period_start TIMESTAMPTZ,
    period_end TIMESTAMPTZ,
    due_date TIMESTAMPTZ,
    paid_at TIMESTAMPTZ,
    line_items JSONB,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_subscription_invoice FOREIGN KEY (subscription_id)
        REFERENCES subscriptions(id)
);

-- Subscription Changes Table
CREATE TABLE IF NOT EXISTS subscription_changes (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    subscription_id VARCHAR(36),
    tenant_id VARCHAR(36) NOT NULL,
    change_type VARCHAR(50),
    previous_plan_id VARCHAR(36),
    new_plan_id VARCHAR(36),
    previous_amount NUMERIC(10, 2),
    new_amount NUMERIC(10, 2),
    prorated_amount NUMERIC(10, 2),
    reason TEXT,
    initiated_by VARCHAR(50),
    change_metadata JSONB,
    effective_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_subscription_change FOREIGN KEY (subscription_id)
        REFERENCES subscriptions(id)
);

-- Paystack Webhooks Table
CREATE TABLE IF NOT EXISTS paystack_webhooks (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    event_type VARCHAR(100),
    paystack_event_id VARCHAR(255) UNIQUE,
    processed BOOLEAN DEFAULT false,
    processing_attempts INTEGER DEFAULT 0,
    last_processing_error TEXT,
    raw_data JSONB,
    signature VARCHAR(255),
    payment_id VARCHAR(36),
    subscription_id VARCHAR(36),
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ
);

-- Usage Tracking Table
CREATE TABLE IF NOT EXISTS usage_tracking (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    tenant_id VARCHAR(36) NOT NULL,
    subscription_id VARCHAR(36),
    period_start TIMESTAMPTZ,
    period_end TIMESTAMPTZ,
    documents_used INTEGER DEFAULT 0,
    websites_used INTEGER DEFAULT 0,
    daily_chats_used INTEGER DEFAULT 0,
    monthly_chats_used INTEGER DEFAULT 0,
    api_calls_made INTEGER DEFAULT 0,
    daily_reset_at TIMESTAMPTZ,
    monthly_reset_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_subscription_usage FOREIGN KEY (subscription_id)
        REFERENCES subscriptions(id)
);

-- Refund Requests Table
CREATE TABLE IF NOT EXISTS refund_requests (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    payment_id VARCHAR(36),
    tenant_id VARCHAR(36) NOT NULL,
    requested_amount NUMERIC(10, 2),
    approved_amount NUMERIC(10, 2),
    currency VARCHAR(3) DEFAULT 'NGN',
    status payment_status DEFAULT 'pending',
    reason TEXT,
    admin_notes TEXT,
    paystack_refund_id VARCHAR(255),
    gateway_response JSONB,
    requested_by VARCHAR(36),
    approved_by VARCHAR(36),
    approved_at TIMESTAMPTZ,
    processed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_payment_refund FOREIGN KEY (payment_id)
        REFERENCES payments(id)
);

-- =====================================================
-- CREATE INDEXES
-- =====================================================

-- Documents indexes
CREATE INDEX IF NOT EXISTS idx_documents_tenant_id ON documents(tenant_id);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents(created_at);

-- Website ingestions indexes
CREATE INDEX IF NOT EXISTS idx_website_ingestions_tenant_id ON website_ingestions(tenant_id);
CREATE INDEX IF NOT EXISTS idx_website_ingestions_status ON website_ingestions(status);

-- Website pages indexes
CREATE INDEX IF NOT EXISTS idx_website_pages_tenant_id ON website_pages(tenant_id);
CREATE INDEX IF NOT EXISTS idx_website_pages_ingestion_id ON website_pages(ingestion_id);
CREATE INDEX IF NOT EXISTS idx_website_pages_content_hash ON website_pages(content_hash);

-- Categories indexes
CREATE INDEX IF NOT EXISTS idx_categories_tenant_id ON document_categories(tenant_id);
CREATE INDEX IF NOT EXISTS idx_categories_parent_id ON document_categories(parent_category_id);

-- Tags indexes
CREATE INDEX IF NOT EXISTS idx_tags_tenant_id ON document_tags(tenant_id);

-- Plans indexes
CREATE INDEX IF NOT EXISTS idx_plans_name ON plans(name);
CREATE INDEX IF NOT EXISTS idx_plans_is_active ON plans(is_active);

-- Subscriptions indexes
CREATE INDEX IF NOT EXISTS idx_subscriptions_tenant_id ON subscriptions(tenant_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_plan_id ON subscriptions(plan_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status);

-- Payments indexes
CREATE INDEX IF NOT EXISTS idx_payments_tenant_id ON payments(tenant_id);
CREATE INDEX IF NOT EXISTS idx_payments_subscription_id ON payments(subscription_id);
CREATE INDEX IF NOT EXISTS idx_payments_paystack_reference ON payments(paystack_reference);
CREATE INDEX IF NOT EXISTS idx_payments_paystack_transaction_id ON payments(paystack_transaction_id);
CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);

-- Payment methods indexes
CREATE INDEX IF NOT EXISTS idx_payment_methods_tenant_id ON payment_methods(tenant_id);
CREATE INDEX IF NOT EXISTS idx_payment_methods_paystack_auth_code ON payment_methods(paystack_authorization_code);

-- Invoices indexes
CREATE INDEX IF NOT EXISTS idx_invoices_tenant_id ON invoices(tenant_id);
CREATE INDEX IF NOT EXISTS idx_invoices_subscription_id ON invoices(subscription_id);
CREATE INDEX IF NOT EXISTS idx_invoices_invoice_number ON invoices(invoice_number);

-- Webhooks indexes
CREATE INDEX IF NOT EXISTS idx_webhooks_event_type ON paystack_webhooks(event_type);
CREATE INDEX IF NOT EXISTS idx_webhooks_paystack_event_id ON paystack_webhooks(paystack_event_id);
CREATE INDEX IF NOT EXISTS idx_webhooks_payment_id ON paystack_webhooks(payment_id);

-- Usage tracking indexes
CREATE INDEX IF NOT EXISTS idx_usage_tracking_tenant_id ON usage_tracking(tenant_id);
CREATE INDEX IF NOT EXISTS idx_usage_tracking_subscription_id ON usage_tracking(subscription_id);

-- =====================================================
-- NOTES
-- =====================================================

/*
IMPORTANT: This schema will be extended by Alembic migrations.
Run the Alembic migrations after executing this script to ensure
all tables and columns are created correctly.

The following will be added by Alembic:
- Tenant model and related tables
- User authentication tables
- Additional columns and constraints
- Any recent schema changes

See: 03-alembic-migrations/ directory for migration scripts
*/