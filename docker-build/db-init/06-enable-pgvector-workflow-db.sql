-- Enable pgvector extension on workflow_db for intent embedding similarity search
\c workflow_db;
CREATE EXTENSION IF NOT EXISTS vector;
