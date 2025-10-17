-- Database initialization script for FactorialBot production environment
-- This script creates the three required databases and the pgvector extension

-- Create databases (PostgreSQL compatible)
-- Note: PostgreSQL doesn't support CREATE DATABASE IF NOT EXISTS
-- These commands will fail if databases already exist, which is expected behavior
CREATE DATABASE vector_db;
CREATE DATABASE chatbot_db;
CREATE DATABASE onboard_db;
CREATE DATABASE authorization_db;
CREATE DATABASE communications_db;
create DATABASE billing_db;

-- Connect to vector_db and enable pgvector extension
\c vector_db;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
GRANT ALL PRIVILEGES ON DATABASE vector_db TO postgres;

-- Connect to chatbot_db and enable extensions
\c chatbot_db;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
GRANT ALL PRIVILEGES ON DATABASE chatbot_db TO postgres;

-- Connect to onboard_db and enable extensions
\c onboard_db;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
GRANT ALL PRIVILEGES ON DATABASE onboard_db TO postgres;

\c authorization_db;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
GRANT ALL PRIVILEGES ON DATABASE authorization_db TO postgres;

\c communications_db;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
GRANT ALL PRIVILEGES ON DATABASE communications_db TO postgres;

\c billing_db;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
GRANT ALL PRIVILEGES ON DATABASE billing_db TO postgres;



-- Log completion
\c postgres;
SELECT 'Database initialization completed successfully!' as status;