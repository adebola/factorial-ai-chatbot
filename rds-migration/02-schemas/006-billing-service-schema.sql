-- =====================================================
-- RDS MIGRATION SCRIPT: Billing Service Schema
-- =====================================================
-- Database: billing_db
-- Purpose: Create billing service schema for plans and subscriptions
-- Dependencies: 01-initialization/001-create-databases-and-extensions.sql
-- Note: This script will be supplemented by Alembic migrations
-- =====================================================

\c billing_db

-- =====================================================
-- CREATE TABLES
-- =====================================================

-- Plans Table
CREATE TABLE IF NOT EXISTS plans (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    document_limit INTEGER DEFAULT -1,
    website_limit INTEGER DEFAULT -1,
    daily_chat_limit INTEGER DEFAULT -1,
    monthly_chat_limit INTEGER DEFAULT -1,
    max_document_size_mb INTEGER,
    max_pages_per_website INTEGER,
    monthly_plan_cost NUMERIC(10, 2) NOT NULL,
    yearly_plan_cost NUMERIC(10, 2) NOT NULL,
    has_trial BOOLEAN DEFAULT false,
    trial_days INTEGER DEFAULT 0,
    has_sentiment_analysis BOOLEAN DEFAULT false,
    has_conversational_workflow BOOLEAN DEFAULT false,
    has_api_access BOOLEAN DEFAULT false,
    has_custom_integrations BOOLEAN DEFAULT false,
    has_on_premise BOOLEAN DEFAULT false,
    analytics_level VARCHAR(20) DEFAULT 'basic',
    support_channels JSONB DEFAULT '["email"]'::jsonb,
    features JSONB,
    is_active BOOLEAN DEFAULT true,
    is_deleted BOOLEAN DEFAULT false,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =====================================================
-- CREATE INDEXES
-- =====================================================

CREATE INDEX IF NOT EXISTS idx_plans_name ON plans(name);
CREATE INDEX IF NOT EXISTS idx_plans_is_active ON plans(is_active);
CREATE INDEX IF NOT EXISTS idx_plans_is_deleted ON plans(is_deleted);

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

-- Trigger for plans
CREATE TRIGGER update_plans_updated_at
    BEFORE UPDATE ON plans
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =====================================================
-- SEED DEFAULT PLANS
-- =====================================================

INSERT INTO plans (
    name, description, document_limit, website_limit, daily_chat_limit, monthly_chat_limit,
    max_document_size_mb, max_pages_per_website,
    monthly_plan_cost, yearly_plan_cost,
    has_trial, trial_days,
    has_sentiment_analysis, has_conversational_workflow, has_api_access,
    has_custom_integrations, has_on_premise,
    analytics_level, support_channels, features
) VALUES
-- Basic Plan (Minimal features for small teams)
(
    'Basic',
    'Essential features for small teams starting with AI chat',
    20,  -- documents
    2,   -- websites
    50,  -- daily chats
    1000, -- monthly chats
    5,   -- max_document_size_mb
    50,  -- max_pages_per_website
    0.00,  -- Free plan
    0.00,
    true,  -- has_trial
    14,    -- trial_days
    false, -- has_sentiment_analysis
    false, -- has_conversational_workflow
    false, -- has_api_access
    false, -- has_custom_integrations
    false, -- has_on_premise
    'basic', -- analytics_level
    '["email"]'::jsonb,
    '{"widget_branding": false, "priority_support": false, "white_label": false}'::jsonb
),

-- Lite Plan (For growing teams)
(
    'Lite',
    'Perfect for growing teams needing more capacity',
    50,  -- documents
    5,   -- websites
    200, -- daily chats
    5000, -- monthly chats
    10,  -- max_document_size_mb
    100, -- max_pages_per_website
    19.99,
    199.99,
    true,
    14,
    false,
    false,
    true,  -- has_api_access
    false,
    false,
    'basic',
    '["email", "chat"]'::jsonb,
    '{"widget_branding": true, "priority_support": false, "white_label": false}'::jsonb
),

-- Pro Plan (For professional teams)
(
    'Pro',
    'Advanced features for professional teams',
    200,  -- documents
    15,   -- websites
    500,  -- daily chats
    15000, -- monthly chats
    25,   -- max_document_size_mb
    500,  -- max_pages_per_website
    49.99,
    499.99,
    true,
    14,
    true,  -- has_sentiment_analysis
    true,  -- has_conversational_workflow
    true,  -- has_api_access
    true,  -- has_custom_integrations
    false,
    'full', -- analytics_level
    '["email", "chat", "phone"]'::jsonb,
    '{"widget_branding": true, "priority_support": true, "white_label": false, "dedicated_account_manager": false}'::jsonb
),

-- Enterprise Plan (For large organizations)
(
    'Enterprise',
    'Complete solution for enterprise organizations with unlimited scale',
    -1,   -- unlimited documents
    -1,   -- unlimited websites
    -1,   -- unlimited daily chats
    -1,   -- unlimited monthly chats
    100,  -- max_document_size_mb
    NULL, -- unlimited pages per website
    199.99,
    1999.99,
    true,
    30,
    true,  -- has_sentiment_analysis
    true,  -- has_conversational_workflow
    true,  -- has_api_access
    true,  -- has_custom_integrations
    true,  -- has_on_premise
    'full',
    '["email", "chat", "phone", "dedicated_slack"]'::jsonb,
    '{"widget_branding": true, "priority_support": true, "white_label": true, "dedicated_account_manager": true, "sla_guarantee": "99.9%", "custom_contract": true}'::jsonb
)
ON CONFLICT (name) DO NOTHING;

-- =====================================================
-- VERIFICATION QUERIES
-- =====================================================

-- Verify table created
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name = 'plans';

-- Verify plans seeded
SELECT
    name,
    monthly_plan_cost,
    document_limit,
    website_limit,
    monthly_chat_limit,
    is_active
FROM plans
ORDER BY monthly_plan_cost;

-- =====================================================
-- NOTES
-- =====================================================

/*
1. PLAN FEATURES:
   - -1 values indicate unlimited usage
   - NULL values indicate no restriction
   - Features stored as JSONB for flexibility

2. PLAN TIERS:
   - Basic: $0/month - Starter features
   - Lite: $19.99/month - Growing teams
   - Pro: $49.99/month - Professional features
   - Enterprise: $199.99/month - Unlimited scale

3. FEATURE FLAGS:
   - has_sentiment_analysis: Advanced AI analytics
   - has_conversational_workflow: Workflow builder access
   - has_api_access: API key for integrations
   - has_custom_integrations: Webhook and custom integrations
   - has_on_premise: On-premise deployment option

4. ANALYTICS LEVELS:
   - basic: Standard metrics (sessions, messages)
   - full: Advanced analytics (sentiment, quality, gaps)

5. SUPPORT CHANNELS:
   - email: Email support only
   - chat: Live chat support
   - phone: Phone support
   - dedicated_slack: Dedicated Slack channel (Enterprise)

6. TRIAL PERIODS:
   - All plans include trial periods
   - Basic/Lite/Pro: 14 days
   - Enterprise: 30 days

7. SOFT DELETE:
   - Plans are never hard deleted
   - is_deleted flag prevents new subscriptions
   - Existing subscriptions continue until expiry

8. SUBSCRIPTION MODEL:
   - Subscription data is stored in onboard_db
   - This database only stores plan definitions
   - Cross-database queries needed for billing reports
*/