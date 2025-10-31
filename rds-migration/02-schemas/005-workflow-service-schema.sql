-- =====================================================
-- RDS MIGRATION SCRIPT: Workflow Service Schema
-- =====================================================
-- Database: workflow_db
-- Purpose: Create workflow service schema for conversational workflows
-- Dependencies: 01-initialization/001-create-databases-and-extensions.sql
-- Note: This script will be supplemented by Alembic migrations
-- =====================================================

\c workflow_db

-- =====================================================
-- CREATE ENUM TYPES
-- =====================================================

DO $$ BEGIN
    CREATE TYPE workflow_status AS ENUM ('draft', 'active', 'inactive', 'archived');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE trigger_type AS ENUM ('message', 'intent', 'keyword', 'manual');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE execution_status AS ENUM ('running', 'completed', 'failed', 'paused', 'cancelled');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE step_type AS ENUM ('message', 'choice', 'input', 'condition', 'action', 'sub_workflow', 'delay');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- =====================================================
-- CREATE TABLES
-- =====================================================

-- Workflows Table
CREATE TABLE IF NOT EXISTS workflows (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    tenant_id VARCHAR(36) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    version VARCHAR(50),
    status workflow_status DEFAULT 'draft',
    definition JSONB NOT NULL,
    trigger_type trigger_type DEFAULT 'manual',
    trigger_config JSONB,
    is_active BOOLEAN DEFAULT false,
    usage_count INTEGER DEFAULT 0,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by VARCHAR(36),
    updated_by VARCHAR(36)
);

-- Workflow Versions Table
CREATE TABLE IF NOT EXISTS workflow_versions (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    workflow_id VARCHAR(36) NOT NULL,
    tenant_id VARCHAR(36) NOT NULL,
    version VARCHAR(50) NOT NULL,
    definition JSONB NOT NULL,
    change_summary TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by VARCHAR(36)
);

-- Workflow Templates Table
CREATE TABLE IF NOT EXISTS workflow_templates (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    category VARCHAR(100),
    tags JSONB,
    definition JSONB NOT NULL,
    default_config JSONB,
    is_public BOOLEAN DEFAULT true,
    usage_count INTEGER DEFAULT 0,
    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by VARCHAR(36)
);

-- Workflow Executions Table
CREATE TABLE IF NOT EXISTS workflow_executions (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    workflow_id VARCHAR(36) NOT NULL,
    tenant_id VARCHAR(36) NOT NULL,
    session_id VARCHAR(36) NOT NULL,
    user_identifier VARCHAR(255),
    status execution_status DEFAULT 'running',
    current_step_id VARCHAR(255),
    variables JSONB,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    error_message TEXT,
    steps_completed INTEGER DEFAULT 0,
    total_steps INTEGER
);

-- Workflow States Table (Maintains conversation state)
CREATE TABLE IF NOT EXISTS workflow_states (
    session_id VARCHAR(36) PRIMARY KEY,
    execution_id VARCHAR(36),
    workflow_id VARCHAR(36) NOT NULL,
    tenant_id VARCHAR(36) NOT NULL,
    current_step_id VARCHAR(255),
    step_context JSONB,
    variables JSONB,
    waiting_for_input VARCHAR(100),
    last_user_message TEXT,
    last_bot_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ
);

-- Step Executions Table
CREATE TABLE IF NOT EXISTS step_executions (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    execution_id VARCHAR(36) NOT NULL,
    workflow_id VARCHAR(36) NOT NULL,
    tenant_id VARCHAR(36) NOT NULL,
    step_id VARCHAR(255) NOT NULL,
    step_type step_type NOT NULL,
    step_config JSONB,
    input_data JSONB,
    output_data JSONB,
    status execution_status DEFAULT 'running',
    error_message TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    duration_ms INTEGER
);

-- Workflow Analytics Table
CREATE TABLE IF NOT EXISTS workflow_analytics (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    workflow_id VARCHAR(36) NOT NULL,
    tenant_id VARCHAR(36) NOT NULL,
    date TIMESTAMPTZ NOT NULL,
    total_executions INTEGER DEFAULT 0,
    completed_executions INTEGER DEFAULT 0,
    failed_executions INTEGER DEFAULT 0,
    avg_completion_time_ms INTEGER,
    avg_steps_completed INTEGER,
    completion_rate INTEGER CHECK (completion_rate >= 0 AND completion_rate <= 100),
    unique_users INTEGER DEFAULT 0,
    returning_users INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Workflow Action Data Table
CREATE TABLE IF NOT EXISTS workflow_action_data (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    tenant_id VARCHAR(36) NOT NULL,
    workflow_id VARCHAR(36) NOT NULL,
    execution_id VARCHAR(36) NOT NULL,
    action_name VARCHAR(255) NOT NULL,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =====================================================
-- CREATE INDEXES
-- =====================================================

-- Workflows indexes
CREATE INDEX IF NOT EXISTS ix_workflows_id ON workflows(id);
CREATE INDEX IF NOT EXISTS ix_workflows_tenant_id ON workflows(tenant_id);
CREATE INDEX IF NOT EXISTS idx_workflows_status ON workflows(status);
CREATE INDEX IF NOT EXISTS idx_workflows_is_active ON workflows(is_active);
CREATE INDEX IF NOT EXISTS idx_workflows_trigger_type ON workflows(trigger_type);

-- Workflow versions indexes
CREATE INDEX IF NOT EXISTS ix_workflow_versions_id ON workflow_versions(id);
CREATE INDEX IF NOT EXISTS ix_workflow_versions_workflow_id ON workflow_versions(workflow_id);
CREATE INDEX IF NOT EXISTS ix_workflow_versions_tenant_id ON workflow_versions(tenant_id);

-- Workflow templates indexes
CREATE INDEX IF NOT EXISTS ix_workflow_templates_id ON workflow_templates(id);
CREATE INDEX IF NOT EXISTS idx_workflow_templates_category ON workflow_templates(category);
CREATE INDEX IF NOT EXISTS idx_workflow_templates_is_public ON workflow_templates(is_public);

-- Workflow executions indexes
CREATE INDEX IF NOT EXISTS ix_workflow_executions_id ON workflow_executions(id);
CREATE INDEX IF NOT EXISTS ix_workflow_executions_workflow_id ON workflow_executions(workflow_id);
CREATE INDEX IF NOT EXISTS ix_workflow_executions_tenant_id ON workflow_executions(tenant_id);
CREATE INDEX IF NOT EXISTS ix_workflow_executions_session_id ON workflow_executions(session_id);
CREATE INDEX IF NOT EXISTS idx_workflow_executions_status ON workflow_executions(status);

-- Workflow states indexes
CREATE INDEX IF NOT EXISTS ix_workflow_states_session_id ON workflow_states(session_id);
CREATE INDEX IF NOT EXISTS ix_workflow_states_execution_id ON workflow_states(execution_id);
CREATE INDEX IF NOT EXISTS ix_workflow_states_workflow_id ON workflow_states(workflow_id);
CREATE INDEX IF NOT EXISTS ix_workflow_states_tenant_id ON workflow_states(tenant_id);
CREATE INDEX IF NOT EXISTS idx_workflow_states_expires_at ON workflow_states(expires_at);

-- Step executions indexes
CREATE INDEX IF NOT EXISTS idx_step_executions_execution_id ON step_executions(execution_id);
CREATE INDEX IF NOT EXISTS idx_step_executions_workflow_id ON step_executions(workflow_id);
CREATE INDEX IF NOT EXISTS idx_step_executions_tenant_id ON step_executions(tenant_id);

-- Workflow analytics indexes
CREATE INDEX IF NOT EXISTS idx_workflow_analytics_workflow_id ON workflow_analytics(workflow_id);
CREATE INDEX IF NOT EXISTS idx_workflow_analytics_tenant_id ON workflow_analytics(tenant_id);
CREATE INDEX IF NOT EXISTS idx_workflow_analytics_date ON workflow_analytics(date);

-- Workflow action data indexes
CREATE INDEX IF NOT EXISTS ix_workflow_action_data_id ON workflow_action_data(id);
CREATE INDEX IF NOT EXISTS ix_workflow_action_data_tenant_id ON workflow_action_data(tenant_id);
CREATE INDEX IF NOT EXISTS ix_workflow_action_data_workflow_id ON workflow_action_data(workflow_id);
CREATE INDEX IF NOT EXISTS ix_workflow_action_data_execution_id ON workflow_action_data(execution_id);
CREATE INDEX IF NOT EXISTS ix_workflow_action_data_tenant_workflow
    ON workflow_action_data(tenant_id, workflow_id);

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

-- Trigger for workflows
CREATE TRIGGER update_workflows_updated_at
    BEFORE UPDATE ON workflows
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Trigger for workflow_templates
CREATE TRIGGER update_workflow_templates_updated_at
    BEFORE UPDATE ON workflow_templates
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Trigger for workflow_states
CREATE TRIGGER update_workflow_states_updated_at
    BEFORE UPDATE ON workflow_states
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =====================================================
-- VERIFICATION QUERIES
-- =====================================================

-- Verify tables created
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name LIKE 'workflow%'
ORDER BY table_name;

-- Verify indexes created
SELECT tablename, indexname FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename LIKE 'workflow%'
ORDER BY tablename, indexname;

-- =====================================================
-- NOTES
-- =====================================================

/*
1. WORKFLOW DEFINITIONS:
   - Stored as JSONB for flexibility
   - Supports YAML/JSON workflow definitions
   - Version history maintained in workflow_versions

2. EXECUTION MODEL:
   - Each workflow execution creates an entry in workflow_executions
   - workflow_states maintains conversation context
   - step_executions tracks individual step completion

3. STATE MANAGEMENT:
   - expires_at used for session cleanup
   - waiting_for_input tracks user input requirements
   - variables JSONB stores workflow-specific data

4. ANALYTICS:
   - Daily aggregation in workflow_analytics
   - Completion rates and performance metrics
   - User engagement tracking

5. MONITORING:
   - Active executions: SELECT COUNT(*) FROM workflow_executions WHERE status = 'running'
   - Failed workflows: SELECT * FROM workflow_executions WHERE status = 'failed'
   - Average completion time: SELECT AVG(EXTRACT(EPOCH FROM (completed_at - started_at)) * 1000) FROM workflow_executions WHERE status = 'completed'

6. CLEANUP:
   - Expire inactive states based on expires_at
   - Archive completed executions older than 90 days
   - Keep workflow definitions and templates indefinitely
*/