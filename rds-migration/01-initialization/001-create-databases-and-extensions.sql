-- =====================================================
-- RDS MIGRATION SCRIPT: Database Initialization
-- =====================================================
-- Purpose: Create all databases and enable required extensions
-- Target: AWS RDS PostgreSQL
-- Author: Auto-generated RDS Migration Script
-- Date: 2025-10-27
-- =====================================================

-- IMPORTANT: Run this script as the master/admin user
-- Ensure you have CREATEDB privileges

-- =====================================================
-- 1. CREATE DATABASES
-- =====================================================

-- Vector Database (Shared Vector Store)
CREATE DATABASE vector_db
    WITH
    OWNER = postgres
    ENCODING = 'UTF8'
    LC_COLLATE = 'en_US.UTF-8'
    LC_CTYPE = 'en_US.UTF-8'
    TEMPLATE = template0;

-- Chat Service Database
CREATE DATABASE chatbot_db
    WITH
    OWNER = postgres
    ENCODING = 'UTF8'
    LC_COLLATE = 'en_US.UTF-8'
    LC_CTYPE = 'en_US.UTF-8'
    TEMPLATE = template0;

-- Onboarding Service Database
CREATE DATABASE onboard_db
    WITH
    OWNER = postgres
    ENCODING = 'UTF8'
    LC_COLLATE = 'en_US.UTF-8'
    LC_CTYPE = 'en_US.UTF-8'
    TEMPLATE = template0;

-- Authorization Server Database
CREATE DATABASE authorization_db
    WITH
    OWNER = postgres
    ENCODING = 'UTF8'
    LC_COLLATE = 'en_US.UTF-8'
    LC_CTYPE = 'en_US.UTF-8'
    TEMPLATE = template0;

-- Communications Service Database
CREATE DATABASE communications_db
    WITH
    OWNER = postgres
    ENCODING = 'UTF8'
    LC_COLLATE = 'en_US.UTF-8'
    LC_CTYPE = 'en_US.UTF-8'
    TEMPLATE = template0;

-- Billing Service Database
CREATE DATABASE billing_db
    WITH
    OWNER = postgres
    ENCODING = 'UTF8'
    LC_COLLATE = 'en_US.UTF-8'
    LC_CTYPE = 'en_US.UTF-8'
    TEMPLATE = template0;

-- Workflow Service Database
CREATE DATABASE workflow_db
    WITH
    OWNER = postgres
    ENCODING = 'UTF8'
    LC_COLLATE = 'en_US.UTF-8'
    LC_CTYPE = 'en_US.UTF-8'
    TEMPLATE = template0;

-- Answer Quality Service Database
CREATE DATABASE answer_quality_db
    WITH
    OWNER = postgres
    ENCODING = 'UTF8'
    LC_COLLATE = 'en_US.UTF-8'
    LC_CTYPE = 'en_US.UTF-8'
    TEMPLATE = template0;

-- =====================================================
-- 2. ENABLE EXTENSIONS - vector_db
-- =====================================================
\c vector_db

-- UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Vector similarity search (pgvector)
-- IMPORTANT: Ensure pgvector is installed on your RDS instance
-- AWS RDS supports pgvector on PostgreSQL 11.1+
CREATE EXTENSION IF NOT EXISTS vector;

-- =====================================================
-- 3. ENABLE EXTENSIONS - chatbot_db
-- =====================================================
\c chatbot_db

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =====================================================
-- 4. ENABLE EXTENSIONS - onboard_db
-- =====================================================
\c onboard_db

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =====================================================
-- 5. ENABLE EXTENSIONS - authorization_db
-- =====================================================
\c authorization_db

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =====================================================
-- 6. ENABLE EXTENSIONS - communications_db
-- =====================================================
\c communications_db

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =====================================================
-- 7. ENABLE EXTENSIONS - billing_db
-- =====================================================
\c billing_db

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =====================================================
-- 8. ENABLE EXTENSIONS - workflow_db
-- =====================================================
\c workflow_db

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =====================================================
-- 9. ENABLE EXTENSIONS - answer_quality_db
-- =====================================================
\c answer_quality_db

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =====================================================
-- VERIFICATION
-- =====================================================

-- Verify databases exist
SELECT datname FROM pg_database
WHERE datname IN (
    'vector_db',
    'chatbot_db',
    'onboard_db',
    'authorization_db',
    'communications_db',
    'billing_db',
    'workflow_db',
    'answer_quality_db'
)
ORDER BY datname;

-- Verify extensions in vector_db
\c vector_db
SELECT extname, extversion FROM pg_extension
WHERE extname IN ('uuid-ossp', 'vector')
ORDER BY extname;

-- =====================================================
-- NOTES FOR RDS DEPLOYMENT
-- =====================================================

/*
1. PGVECTOR INSTALLATION:
   - Ensure pgvector is available in your RDS instance
   - For AWS RDS PostgreSQL 15+: pgvector is available by default
   - For older versions: Contact AWS support or upgrade to PostgreSQL 15+
   - Test with: CREATE EXTENSION vector;

2. PRIVILEGES:
   - Run this script with rds_superuser or master user
   - Grant appropriate privileges to application users after creation

3. CONNECTION STRINGS:
   After running this script, update your .env files with:

   vector_db:
   VECTOR_DATABASE_URL=postgresql://user:password@your-rds-endpoint:5432/vector_db

   chatbot_db (chat-service):
   DATABASE_URL=postgresql://user:password@your-rds-endpoint:5432/chatbot_db

   onboard_db (onboarding-service):
   DATABASE_URL=postgresql://user:password@your-rds-endpoint:5432/onboard_db

   authorization_db (authorization-server):
   DATABASE_URL=postgresql://user:password@your-rds-endpoint:5432/authorization_db

   communications_db:
   DATABASE_URL=postgresql://user:password@your-rds-endpoint:5432/communications_db

   billing_db:
   DATABASE_URL=postgresql://user:password@your-rds-endpoint:5432/billing_db

   workflow_db:
   DATABASE_URL=postgresql://user:password@your-rds-endpoint:5432/workflow_db

   answer_quality_db:
   DATABASE_URL=postgresql://user:password@your-rds-endpoint:5432/answer_quality_db

4. RESOURCE SIZING:
   - Recommended minimum for production: db.t3.medium (2 vCPU, 4GB RAM)
   - Storage: At least 100GB GP3 SSD with auto-scaling enabled
   - IOPS: Minimum 3000 for vector operations

5. PARAMETER GROUPS:
   Recommended PostgreSQL parameters for vector operations:
   - shared_buffers: 25% of total memory
   - effective_cache_size: 75% of total memory
   - maintenance_work_mem: 2GB (for index building)
   - max_connections: 200 (adjust based on service count)

6. SECURITY:
   - Enable encryption at rest
   - Enable encryption in transit (SSL/TLS)
   - Configure security groups to allow only application server IPs
   - Use AWS Secrets Manager for database credentials
   - Enable automated backups with 7-day retention minimum

7. MONITORING:
   - Enable Enhanced Monitoring
   - Set up CloudWatch alarms for:
     * CPU utilization > 80%
     * Free storage space < 20%
     * Database connections > 80% of max
     * Read/Write latency spikes

*/