-- =====================================================
-- RDS MIGRATION SCRIPT: Chat Service Schema
-- =====================================================
-- Database: chatbot_db
-- Purpose: Create chat service schema for sessions and messages
-- Dependencies: 01-initialization/001-create-databases-and-extensions.sql
-- =====================================================

\c chatbot_db

-- =====================================================
-- CREATE TABLES
-- =====================================================

-- Chat Sessions Table
CREATE TABLE IF NOT EXISTS chat_sessions (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    tenant_id VARCHAR(255) NOT NULL,
    session_id VARCHAR(255) NOT NULL UNIQUE,
    user_identifier VARCHAR(255),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_activity TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Chat Messages Table
CREATE TABLE IF NOT EXISTS chat_messages (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    tenant_id VARCHAR(255) NOT NULL,
    session_id VARCHAR(255) NOT NULL,
    message_type VARCHAR(20) NOT NULL CHECK (message_type IN ('user', 'assistant')),
    content TEXT NOT NULL,
    message_metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =====================================================
-- CREATE INDEXES
-- =====================================================

-- Sessions indexes
CREATE INDEX IF NOT EXISTS idx_sessions_tenant_id
    ON chat_sessions(tenant_id);

CREATE INDEX IF NOT EXISTS idx_sessions_session_id
    ON chat_sessions(session_id);

CREATE INDEX IF NOT EXISTS idx_sessions_is_active
    ON chat_sessions(is_active);

CREATE INDEX IF NOT EXISTS idx_sessions_created_at
    ON chat_sessions(created_at);

-- Messages indexes
CREATE INDEX IF NOT EXISTS idx_messages_tenant_id
    ON chat_messages(tenant_id);

CREATE INDEX IF NOT EXISTS idx_messages_session_id
    ON chat_messages(session_id);

CREATE INDEX IF NOT EXISTS idx_messages_message_type
    ON chat_messages(message_type);

CREATE INDEX IF NOT EXISTS idx_messages_created_at
    ON chat_messages(created_at);

-- Composite index for common query pattern
CREATE INDEX IF NOT EXISTS idx_messages_session_created
    ON chat_messages(session_id, created_at DESC);

-- =====================================================
-- CREATE UPDATE TRIGGER
-- =====================================================

-- Function to update last_activity on sessions
CREATE OR REPLACE FUNCTION update_session_activity()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE chat_sessions
    SET last_activity = now()
    WHERE session_id = NEW.session_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to update session activity when new message arrives
CREATE TRIGGER update_session_activity_on_message
    AFTER INSERT ON chat_messages
    FOR EACH ROW
    EXECUTE FUNCTION update_session_activity();

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
  AND table_name IN ('chat_sessions', 'chat_messages')
ORDER BY table_name;

-- Verify indexes created
SELECT tablename, indexname FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN ('chat_sessions', 'chat_messages')
ORDER BY tablename, indexname;

-- =====================================================
-- NOTES
-- =====================================================

/*
1. SESSION MANAGEMENT:
   - Sessions are created when WebSocket connections are established
   - last_activity is automatically updated on every message
   - Inactive sessions can be cleaned up based on last_activity

2. MESSAGE STORAGE:
   - message_metadata stores RAG sources, context, and other structured data
   - JSONB type allows efficient querying of metadata fields
   - Consider partitioning by created_at for high-volume deployments

3. CLEANUP RECOMMENDATIONS:
   - Archive messages older than 90 days to cold storage
   - Delete inactive sessions after 30 days of no activity
   - Use pg_cron or external scheduler for cleanup jobs

4. MONITORING:
   - Track active sessions: SELECT COUNT(*) FROM chat_sessions WHERE is_active = true
   - Messages per day: SELECT DATE(created_at), COUNT(*) FROM chat_messages GROUP BY DATE(created_at)
   - Average messages per session: SELECT AVG(msg_count) FROM (SELECT session_id, COUNT(*) as msg_count FROM chat_messages GROUP BY session_id) t
*/