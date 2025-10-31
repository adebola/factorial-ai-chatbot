-- =====================================================
-- RDS MIGRATION SCRIPT: Answer Quality Service Schema
-- =====================================================
-- Database: answer_quality_db
-- Purpose: Create answer quality service schema for monitoring and analytics
-- Dependencies: 01-initialization/001-create-databases-and-extensions.sql
-- Note: This script will be supplemented by Alembic migrations
-- =====================================================

\c answer_quality_db

-- =====================================================
-- CREATE ENUM TYPES
-- =====================================================

DO $$ BEGIN
    CREATE TYPE feedback_type AS ENUM ('helpful', 'not_helpful');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE sentiment_type AS ENUM ('positive', 'neutral', 'negative', 'frustrated');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE gap_status AS ENUM ('detected', 'acknowledged', 'resolved');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE alert_severity AS ENUM ('low', 'medium', 'high', 'critical');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE job_status AS ENUM ('pending', 'running', 'completed', 'failed');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- =====================================================
-- CREATE TABLES
-- =====================================================

-- Answer Feedback Table
CREATE TABLE IF NOT EXISTS answer_feedback (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    tenant_id VARCHAR(36) NOT NULL,
    session_id VARCHAR(36) NOT NULL,
    message_id VARCHAR(36) NOT NULL,
    feedback_type feedback_type NOT NULL,
    feedback_comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- RAG Quality Metrics Table
CREATE TABLE IF NOT EXISTS rag_quality_metrics (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    tenant_id VARCHAR(36) NOT NULL,
    session_id VARCHAR(36) NOT NULL,
    message_id VARCHAR(36) NOT NULL UNIQUE,
    retrieval_score FLOAT CHECK (retrieval_score >= 0 AND retrieval_score <= 1),
    documents_retrieved INTEGER,
    answer_confidence FLOAT CHECK (answer_confidence >= 0 AND answer_confidence <= 1),
    sources_cited INTEGER,
    answer_length INTEGER,
    response_time_ms INTEGER,
    basic_sentiment sentiment_type,
    sentiment_confidence FLOAT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Session Quality Table
CREATE TABLE IF NOT EXISTS session_quality (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    tenant_id VARCHAR(36) NOT NULL,
    session_id VARCHAR(36) NOT NULL UNIQUE,
    total_messages INTEGER DEFAULT 0,
    messages_with_feedback INTEGER DEFAULT 0,
    helpful_count INTEGER DEFAULT 0,
    not_helpful_count INTEGER DEFAULT 0,
    avg_retrieval_score FLOAT,
    avg_confidence_score FLOAT,
    avg_response_time_ms INTEGER,
    session_success BOOLEAN,
    success_indicators JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Knowledge Gaps Table
CREATE TABLE IF NOT EXISTS knowledge_gaps (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    tenant_id VARCHAR(36) NOT NULL,
    question_pattern TEXT NOT NULL,
    example_questions JSONB,
    occurrence_count INTEGER DEFAULT 1,
    avg_confidence FLOAT,
    negative_feedback_count INTEGER DEFAULT 0,
    status gap_status DEFAULT 'detected',
    resolved_at TIMESTAMPTZ,
    resolution_notes TEXT,
    first_detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_occurrence_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Alert Rules Table
CREATE TABLE IF NOT EXISTS alert_rules (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    tenant_id VARCHAR(36) NOT NULL,
    name VARCHAR(255) NOT NULL,
    rule_type VARCHAR(50) NOT NULL,
    description VARCHAR(500),
    threshold_value FLOAT NOT NULL,
    check_interval_hours INTEGER DEFAULT 24,
    min_sample_size INTEGER DEFAULT 10,
    notification_channels JSONB DEFAULT '["email"]'::jsonb,
    notification_recipients JSONB,
    throttle_minutes INTEGER DEFAULT 1440,
    last_triggered_at TIMESTAMPTZ,
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by VARCHAR(36)
);

-- Alert History Table
CREATE TABLE IF NOT EXISTS alert_history (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    tenant_id VARCHAR(36) NOT NULL,
    rule_id VARCHAR(36) NOT NULL,
    rule_name VARCHAR(255),
    rule_type VARCHAR(50),
    severity alert_severity DEFAULT 'medium',
    alert_message TEXT NOT NULL,
    alert_data JSONB,
    notification_sent BOOLEAN DEFAULT false,
    notification_channels_used JSONB,
    notification_response JSONB,
    notification_error TEXT,
    triggered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ
);

-- Job Execution Logs Table
CREATE TABLE IF NOT EXISTS job_execution_logs (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    tenant_id VARCHAR(36),
    job_name VARCHAR(100) NOT NULL,
    job_type VARCHAR(50),
    status job_status DEFAULT 'pending',
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    duration_ms INTEGER,
    result_summary JSONB,
    error_message TEXT,
    error_details JSONB,
    triggered_by VARCHAR(50),
    triggered_by_user_id VARCHAR(36)
);

-- =====================================================
-- CREATE INDEXES
-- =====================================================

-- Feedback indexes
CREATE INDEX IF NOT EXISTS ix_answer_feedback_id ON answer_feedback(id);
CREATE INDEX IF NOT EXISTS ix_answer_feedback_message_id ON answer_feedback(message_id);
CREATE INDEX IF NOT EXISTS ix_answer_feedback_session_id ON answer_feedback(session_id);
CREATE INDEX IF NOT EXISTS ix_answer_feedback_tenant_id ON answer_feedback(tenant_id);
CREATE INDEX IF NOT EXISTS idx_feedback_created_at ON answer_feedback(created_at);

-- Quality metrics indexes
CREATE INDEX IF NOT EXISTS ix_rag_quality_metrics_id ON rag_quality_metrics(id);
CREATE INDEX IF NOT EXISTS ix_rag_quality_metrics_message_id ON rag_quality_metrics(message_id);
CREATE INDEX IF NOT EXISTS ix_rag_quality_metrics_session_id ON rag_quality_metrics(session_id);
CREATE INDEX IF NOT EXISTS ix_rag_quality_metrics_tenant_id ON rag_quality_metrics(tenant_id);
CREATE INDEX IF NOT EXISTS idx_quality_metrics_created_at ON rag_quality_metrics(created_at);
CREATE INDEX IF NOT EXISTS idx_quality_metrics_sentiment ON rag_quality_metrics(basic_sentiment);

-- Session quality indexes
CREATE INDEX IF NOT EXISTS ix_session_quality_id ON session_quality(id);
CREATE INDEX IF NOT EXISTS ix_session_quality_session_id ON session_quality(session_id);
CREATE INDEX IF NOT EXISTS ix_session_quality_tenant_id ON session_quality(tenant_id);

-- Knowledge gaps indexes
CREATE INDEX IF NOT EXISTS ix_knowledge_gaps_id ON knowledge_gaps(id);
CREATE INDEX IF NOT EXISTS ix_knowledge_gaps_tenant_id ON knowledge_gaps(tenant_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_gaps_status ON knowledge_gaps(status);
CREATE INDEX IF NOT EXISTS idx_knowledge_gaps_occurrence_count ON knowledge_gaps(occurrence_count DESC);

-- Alert rules indexes
CREATE INDEX IF NOT EXISTS ix_alert_rules_id ON alert_rules(id);
CREATE INDEX IF NOT EXISTS ix_alert_rules_tenant_id ON alert_rules(tenant_id);
CREATE INDEX IF NOT EXISTS idx_alert_rules_enabled ON alert_rules(enabled);
CREATE INDEX IF NOT EXISTS idx_alert_rules_rule_type ON alert_rules(rule_type);

-- Alert history indexes
CREATE INDEX IF NOT EXISTS ix_alert_history_id ON alert_history(id);
CREATE INDEX IF NOT EXISTS ix_alert_history_rule_id ON alert_history(rule_id);
CREATE INDEX IF NOT EXISTS ix_alert_history_tenant_id ON alert_history(tenant_id);
CREATE INDEX IF NOT EXISTS idx_alert_history_triggered_at ON alert_history(triggered_at);

-- Job logs indexes
CREATE INDEX IF NOT EXISTS ix_job_execution_logs_id ON job_execution_logs(id);
CREATE INDEX IF NOT EXISTS ix_job_execution_logs_job_name ON job_execution_logs(job_name);
CREATE INDEX IF NOT EXISTS ix_job_execution_logs_tenant_id ON job_execution_logs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_job_logs_status ON job_execution_logs(status);
CREATE INDEX IF NOT EXISTS idx_job_logs_started_at ON job_execution_logs(started_at);

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

-- Trigger for session_quality
CREATE TRIGGER update_session_quality_updated_at
    BEFORE UPDATE ON session_quality
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Trigger for alert_rules
CREATE TRIGGER update_alert_rules_updated_at
    BEFORE UPDATE ON alert_rules
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =====================================================
-- VERIFICATION QUERIES
-- =====================================================

-- Verify tables created
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN (
    'answer_feedback',
    'rag_quality_metrics',
    'session_quality',
    'knowledge_gaps',
    'alert_rules',
    'alert_history',
    'job_execution_logs'
  )
ORDER BY table_name;

-- Verify indexes created
SELECT tablename, indexname FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;

-- =====================================================
-- NOTES
-- =====================================================

/*
1. QUALITY MONITORING:
   - answer_feedback captures user satisfaction
   - rag_quality_metrics tracks AI response quality
   - session_quality aggregates session-level metrics
   - Metrics computed in real-time during chat

2. SENTIMENT ANALYSIS:
   - basic_sentiment uses VADER (rule-based)
   - sentiment_confidence indicates reliability
   - Enhanced sentiment analysis available in Pro+ plans

3. KNOWLEDGE GAPS:
   - Automatically detected when:
     * Low retrieval scores (< 0.3)
     * Low confidence (< 0.5)
     * Negative feedback
   - question_pattern stores generalized question
   - example_questions contains actual user queries

4. ALERT SYSTEM:
   - alert_rules define thresholds and notification settings
   - alert_history logs all triggered alerts
   - Throttling prevents alert spam
   - Supports email, webhook, Slack notifications

5. JOB SCHEDULING:
   - job_execution_logs tracks all scheduled jobs
   - Jobs run hourly/daily via APScheduler
   - Monitors: quality trends, gap detection, alert evaluation

6. DEFAULT ALERT RULES:
   Create these via API or manually:
   - Quality Drop: avg_confidence < 0.5 over 24h
   - New Gaps: 5+ occurrences in 24h
   - High Negative Feedback: >30% not_helpful in 24h
   - Session Degradation: avg_session_success < 0.6 in 24h

7. ANALYTICS QUERIES:
   - Overall quality: SELECT AVG(answer_confidence) FROM rag_quality_metrics WHERE tenant_id = ?
   - Feedback ratio: SELECT feedback_type, COUNT(*) FROM answer_feedback WHERE tenant_id = ? GROUP BY feedback_type
   - Active gaps: SELECT * FROM knowledge_gaps WHERE tenant_id = ? AND status != 'resolved' ORDER BY occurrence_count DESC
   - Recent alerts: SELECT * FROM alert_history WHERE tenant_id = ? ORDER BY triggered_at DESC LIMIT 10

8. CLEANUP:
   - Archive metrics older than 180 days
   - Keep alert_history for 90 days
   - Keep knowledge_gaps indefinitely (historical value)
   - Purge job_execution_logs older than 30 days
*/