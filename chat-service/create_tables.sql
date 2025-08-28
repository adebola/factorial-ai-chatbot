-- Create chat_sessions and chat_messages tables
-- Generated from Alembic migration: f06fba976192_create_chat_sessions_and_chat_messages_tables

-- Enable UUID extension for PostgreSQL (if not already enabled)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create chat_sessions table
CREATE TABLE chat_sessions (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    tenant_id VARCHAR(255) NOT NULL,
    session_id VARCHAR(255) NOT NULL UNIQUE,
    user_identifier VARCHAR(255),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    last_activity TIMESTAMP WITH TIME ZONE
);

-- Create indexes for chat_sessions
CREATE INDEX ix_chat_sessions_id ON chat_sessions (id);
CREATE INDEX ix_chat_sessions_tenant_id ON chat_sessions (tenant_id);
CREATE UNIQUE INDEX ix_chat_sessions_session_id ON chat_sessions (session_id);

-- Create chat_messages table
CREATE TABLE chat_messages (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    tenant_id VARCHAR(255) NOT NULL,
    session_id VARCHAR(255) NOT NULL,
    message_type VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    message_metadata JSON,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Create indexes for chat_messages
CREATE INDEX ix_chat_messages_id ON chat_messages (id);
CREATE INDEX ix_chat_messages_tenant_id ON chat_messages (tenant_id);
CREATE INDEX ix_chat_messages_session_id ON chat_messages (session_id);

-- Add some comments for documentation
COMMENT ON TABLE chat_sessions IS 'WebSocket chat sessions for tracking user conversations';
COMMENT ON TABLE chat_messages IS 'Individual messages within chat sessions';
COMMENT ON COLUMN chat_messages.message_type IS 'Either ''user'' or ''assistant''';
COMMENT ON COLUMN chat_messages.message_metadata IS 'Additional context like sources, user_identifier, etc.';