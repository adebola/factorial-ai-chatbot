-- Create observability database for the Observability Agent Service
SELECT 'CREATE DATABASE observability_db'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'observability_db')\gexec

\c observability_db;

-- Ensure uuid-ossp extension is available
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
