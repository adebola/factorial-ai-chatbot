-- Initialize pgvector extension for FactorialBot
-- This script runs automatically when PostgreSQL container starts

-- Create the vector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create schemas for better organization
CREATE SCHEMA IF NOT EXISTS vectors;
CREATE SCHEMA IF NOT EXISTS chat_service;
CREATE SCHEMA IF NOT EXISTS onboarding;

-- Set search path to include all schemas
ALTER DATABASE chatbot_db SET search_path TO public, vectors, chat_service, onboarding;

-- Grant permissions ("user" is a reserved word, so we need to quote it)
GRANT ALL ON SCHEMA vectors TO "user";
GRANT ALL ON SCHEMA chat_service TO "user";  
GRANT ALL ON SCHEMA onboarding TO "user";

-- Show pgvector version
SELECT extversion FROM pg_extension WHERE extname = 'vector';