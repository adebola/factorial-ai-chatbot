# ChatCraft RDS Migration Guide

Complete guide for migrating FactorialBot database infrastructure from Docker PostgreSQL to AWS RDS.

## Table of Contents

1. [Overview](#overview)
2. [Pre-Migration Checklist](#pre-migration-checklist)
3. [RDS Setup](#rds-setup)
4. [Migration Process](#migration-process)
5. [Post-Migration Tasks](#post-migration-tasks)
6. [Rollback Plan](#rollback-plan)
7. [Troubleshooting](#troubleshooting)
8. [Performance Tuning](#performance-tuning)

---

## Overview

### Migration Scope

This migration moves **8 PostgreSQL databases** from Docker containers to AWS RDS:

| Database | Purpose | Size Estimate | Critical Data |
|----------|---------|---------------|---------------|
| `vector_db` | Document embeddings (pgvector) | Large (GB-TB) | Yes - Vector embeddings |
| `chatbot_db` | Chat sessions & messages | Medium (MB-GB) | Yes - Chat history |
| `onboard_db` | Tenants, users, subscriptions | Medium (MB-GB) | Critical - Customer data |
| `authorization_db` | OAuth2 authentication | Small (MB) | Critical - Auth data |
| `communications_db` | Email/SMS delivery | Medium (MB-GB) | Yes - Message logs |
| `billing_db` | Subscription plans | Small (MB) | Critical - Billing data |
| `workflow_db` | Conversational workflows | Medium (MB-GB) | Yes - Workflow state |
| `answer_quality_db` | Quality monitoring | Small-Medium (MB) | No - Analytics only |

### Migration Strategy

- **Approach:** Schema-first, then data migration
- **Downtime:** Required for data migration consistency
- **Duration:** 2-6 hours depending on data volume
- **Risk Level:** Medium (comprehensive rollback plan included)

### Directory Structure

```
rds-migration/
├── 01-initialization/           # Database & extension creation
├── 02-schemas/                  # Table & index creation
├── 03-alembic-migrations/       # Alembic migration guide
├── 04-data-migration/           # Data transfer scripts
├── 05-validation/               # Validation & testing
├── scripts/                     # Orchestration scripts
├── logs/                        # Migration logs (created during run)
└── README.md                    # This file
```

---

## Pre-Migration Checklist

### 1. Infrastructure Preparation

- [ ] AWS RDS PostgreSQL instance provisioned
- [ ] RDS instance version matches source (PostgreSQL 13+)
- [ ] pgvector extension available on RDS (PostgreSQL 15+ recommended)
- [ ] Security group configured to allow connections from:
  - [ ] Your local machine (for migration)
  - [ ] Application servers (EC2/ECS/etc.)
- [ ] RDS master password securely stored (AWS Secrets Manager recommended)
- [ ] Sufficient storage provisioned (3x current data size recommended)
- [ ] Enhanced Monitoring enabled
- [ ] Automated backups configured (7+ day retention)

### 2. Network & Access

- [ ] VPC and subnet configuration verified
- [ ] Internet Gateway or NAT Gateway for external access (if needed)
- [ ] RDS endpoint DNS resolvable from migration machine
- [ ] Test connection: `psql -h your-rds-endpoint -U postgres -d postgres`
- [ ] Application servers can reach RDS (test from EC2 if deployed)

### 3. Backup & Safety

- [ ] Full backup of current Docker PostgreSQL data
  ```bash
  docker-compose exec postgres pg_dumpall -U postgres -f /tmp/full_backup.sql
  ```
- [ ] Backup files stored securely (S3, local storage)
- [ ] Rollback plan documented and tested
- [ ] Maintenance window scheduled (low traffic period)
- [ ] Stakeholders notified of scheduled downtime

### 4. Tools & Dependencies

- [ ] PostgreSQL client tools installed (psql, pg_dump, pg_restore)
  ```bash
  # macOS
  brew install postgresql@15

  # Ubuntu
  sudo apt install postgresql-client-15
  ```
- [ ] Python 3.8+ installed
- [ ] Alembic installed for all services
  ```bash
  pip install alembic psycopg2-binary sqlalchemy
  ```
- [ ] Sufficient disk space for backups (10GB+ recommended)

### 5. Environment Configuration

- [ ] RDS connection details documented:
  ```
  RDS_ENDPOINT=your-instance.region.rds.amazonaws.com
  RDS_PORT=5432
  RDS_MASTER_USER=postgres
  RDS_MASTER_PASSWORD=<secure-password>
  ```
- [ ] Source PostgreSQL accessible
- [ ] Migration scripts reviewed and tested in staging

---

## RDS Setup

### Recommended RDS Configuration

#### Instance Specifications

- **Instance Class:** `db.t3.medium` (minimum), `db.m5.large` (production)
- **Storage:** 100GB GP3 SSD minimum
  - IOPS: 3000 baseline (increase for vector operations)
  - Throughput: 125 MB/s
  - Autoscaling: Enable (max 500GB)
- **Engine:** PostgreSQL 15.x (for native pgvector support)
- **Multi-AZ:** Yes (for production)

#### Parameter Group Settings

Create custom parameter group with these settings:

```
shared_buffers = 25% of RAM (e.g., 1GB for 4GB instance)
effective_cache_size = 75% of RAM (e.g., 3GB for 4GB instance)
maintenance_work_mem = 2GB (for index building)
max_connections = 200
work_mem = 16MB
random_page_cost = 1.1 (for SSD)
effective_io_concurrency = 200
```

#### Security Configuration

```
# Security Group Rules
Inbound:
- PostgreSQL (5432) from application security group
- PostgreSQL (5432) from your IP (temporary, for migration)

Outbound:
- All traffic (default)

# Encryption
- Encryption at rest: Enabled (KMS)
- Encryption in transit: SSL/TLS required
```

#### Backup Configuration

```
Backup Retention: 7 days
Backup Window: 03:00-04:00 UTC (low traffic period)
Maintenance Window: Sunday 04:00-05:00 UTC
Auto Minor Version Upgrade: No (manual control)
```

### Creating the RDS Instance

#### Via AWS Console

1. Go to RDS Console → Create Database
2. Choose PostgreSQL engine (version 15.x)
3. Select instance size and storage
4. Configure VPC, security groups
5. Set master username and password
6. Enable Enhanced Monitoring
7. Review and create

#### Via AWS CLI

```bash
aws rds create-db-instance \
  --db-instance-identifier factorialbot-prod \
  --db-instance-class db.t3.medium \
  --engine postgres \
  --engine-version 15.4 \
  --master-username postgres \
  --master-user-password <secure-password> \
  --allocated-storage 100 \
  --storage-type gp3 \
  --iops 3000 \
  --storage-encrypted \
  --vpc-security-group-ids sg-xxxxxxxx \
  --db-subnet-group-name my-db-subnet-group \
  --backup-retention-period 7 \
  --preferred-backup-window "03:00-04:00" \
  --preferred-maintenance-window "sun:04:00-sun:05:00" \
  --enable-cloudwatch-logs-exports '["postgresql"]' \
  --deletion-protection \
  --tags Key=Project,Value=FactorialBot Key=Environment,Value=Production
```

### Verify pgvector Extension

```bash
psql -h your-rds-endpoint -U postgres -d postgres

# Test pgvector availability
CREATE EXTENSION IF NOT EXISTS vector;
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';

# Should return: vector | 0.5.x (or later)
```

---

## Migration Process

### Option 1: Automated Migration (Recommended)

Use the orchestration script for end-to-end migration:

```bash
# Set environment variables
export RDS_ENDPOINT=your-rds-endpoint.region.rds.amazonaws.com
export RDS_PORT=5432
export RDS_MASTER_USER=postgres
export RDS_MASTER_PASSWORD=your-secure-password

# Run complete migration
cd rds-migration/scripts
./run-migration.sh
```

The script will:
1. Create all databases and extensions
2. Create schemas and tables
3. Run Alembic migrations
4. Migrate data from Docker (optional, interactive)
5. Run validation checks
6. Generate updated .env files

**Estimated Duration:** 2-6 hours

---

### Option 2: Manual Step-by-Step Migration

#### Step 1: Create Databases and Extensions

```bash
cd rds-migration

# Set password for psql
export PGPASSWORD=your-rds-password

# Run database creation script
psql -h your-rds-endpoint -U postgres -d postgres \
  -f 01-initialization/001-create-databases-and-extensions.sql
```

**Verify:**
```sql
-- List databases
SELECT datname FROM pg_database WHERE datname IN (
  'vector_db', 'chatbot_db', 'onboard_db', 'authorization_db',
  'communications_db', 'billing_db', 'workflow_db', 'answer_quality_db'
);

-- Check extensions in vector_db
\c vector_db
SELECT extname FROM pg_extension;
```

#### Step 2: Create Database Schemas

```bash
# Execute schema scripts
psql -h your-rds-endpoint -U postgres \
  -f 02-schemas/001-vector-db-schema.sql

psql -h your-rds-endpoint -U postgres \
  -f 02-schemas/002-chat-service-schema.sql

psql -h your-rds-endpoint -U postgres \
  -f 02-schemas/003-onboarding-service-schema.sql

psql -h your-rds-endpoint -U postgres \
  -f 02-schemas/004-communications-service-schema.sql

psql -h your-rds-endpoint -U postgres \
  -f 02-schemas/005-workflow-service-schema.sql

psql -h your-rds-endpoint -U postgres \
  -f 02-schemas/006-billing-service-schema.sql

psql -h your-rds-endpoint -U postgres \
  -f 02-schemas/007-answer-quality-service-schema.sql

psql -h your-rds-endpoint -U postgres \
  -f 02-schemas/008-authorization-server-schema.sql
```

**Verify:**
```sql
-- Check tables in vector_db
\c vector_db
\dt vectors.*

-- Check indexes
\di vectors.*
```

#### Step 3: Run Alembic Migrations (Python Services Only)

See detailed instructions in `03-alembic-migrations/README.md`

```bash
# Example for communications-service
cd ../communications-service

# Update .env with RDS connection
DATABASE_URL=postgresql://postgres:password@your-rds-endpoint:5432/communications_db

# Run migrations
alembic upgrade head

# Verify
alembic current
```

Repeat for all **Python services** with Alembic:
- billing-service
- communications-service
- workflow-service
- answer-quality-service
- onboarding-service

**Note:** Authorization server (Spring Boot) uses **Flyway**, which is already consolidated in `008-authorization-server-schema.sql`. Spring Boot will recognize the `flyway_schema_history` table and skip re-running migrations V1-V9.

#### Step 4: Migrate Data

See detailed instructions in `04-data-migration/README.md`

```bash
cd rds-migration/04-data-migration

# Configure source and target
export SOURCE_HOST=localhost
export SOURCE_PORT=5432
export SOURCE_USER=postgres
export SOURCE_PASSWORD=password
export TARGET_HOST=your-rds-endpoint
export TARGET_PORT=5432
export TARGET_USER=postgres
export TARGET_PASSWORD=your-rds-password

# Run migration
./migrate-data.sh
```

**Estimated Duration:**
- Small databases (<100MB): 5-15 minutes each
- Medium databases (100MB-1GB): 15-60 minutes each
- Large databases (>1GB): 1-4 hours each

**What to Monitor:**
- Disk space usage (backup directory)
- Network bandwidth
- RDS CPU and memory usage
- Migration log output

#### Step 5: Validate Migration

```bash
cd ../05-validation

# Set RDS credentials
export RDS_HOST=your-rds-endpoint
export RDS_PORT=5432
export RDS_USER=postgres
export RDS_PASSWORD=your-rds-password

# Run validation
./validate.sh
```

**Expected Output:**
```
✓ PASS RDS connectivity established
✓ PASS Database vector_db exists
✓ PASS Extension pgvector installed in vector_db
...
=========================================
VALIDATION SUMMARY
=========================================
Passed:   XX
Failed:   0
Warnings: X
=========================================
```

---

## Post-Migration Tasks

### 1. Update Application Configuration

Update `.env` files for all services:

#### Onboarding Service
```env
DATABASE_URL=postgresql://user:password@your-rds-endpoint:5432/onboard_db
VECTOR_DATABASE_URL=postgresql://user:password@your-rds-endpoint:5432/vector_db
```

#### Chat Service
```env
DATABASE_URL=postgresql://user:password@your-rds-endpoint:5432/chatbot_db
VECTOR_DATABASE_URL=postgresql://user:password@your-rds-endpoint:5432/vector_db
```

#### Communications Service
```env
DATABASE_URL=postgresql://user:password@your-rds-endpoint:5432/communications_db
```

#### Workflow Service
```env
DATABASE_URL=postgresql://user:password@your-rds-endpoint:5432/workflow_db
```

#### Billing Service
```env
DATABASE_URL=postgresql://user:password@your-rds-endpoint:5432/billing_db
```

#### Answer Quality Service
```env
DATABASE_URL=postgresql://user:password@your-rds-endpoint:5432/answer_quality_db
```

#### Authorization Server (Spring Boot)
```properties
spring.datasource.url=jdbc:postgresql://your-rds-endpoint:5432/authorization_db
spring.datasource.username=postgres
spring.datasource.password=your-password

# Flyway configuration (optional - for new migrations only)
spring.flyway.baseline-on-migrate=true
spring.flyway.baseline-version=9
```

**Important:** The schema script already created `flyway_schema_history` with version 9 (consolidated V1-V9). Spring Boot will detect this and only run new migrations (V10+).

### 2. Test Service Connectivity

```bash
# Start each service and test database connectivity

# Onboarding Service
cd onboarding-service
uvicorn app.main:app --reload
# Test: curl http://localhost:8001/api/v1/health

# Chat Service
cd ../chat-service
uvicorn app.main:app --reload
# Test WebSocket connection

# Repeat for all services
```

### 3. Run Smoke Tests

```bash
# Test critical functionality

# 1. OAuth2 Authentication (Authorization Server)
curl -X POST http://localhost:9000/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password" \
  -d "username=admin" \
  -d "password=admin123" \
  -d "client_id=webclient" \
  -d "client_secret=secret"

# 2. User Registration
curl -X POST http://localhost:8001/api/v1/tenants/register \
  -H "Content-Type: application/json" \
  -d '{"organization_name": "Test Org", "email": "test@example.com"}'

# 3. Document Upload
curl -X POST http://localhost:8001/api/v1/documents/upload \
  -H "Authorization: Bearer <token>" \
  -F "file=@test.pdf"

# 4. Chat Session
# Connect to WebSocket and send message

# 5. Vector Search
# Verify chat responses include relevant sources
```

**Default Test Credentials (Authorization Server):**
- Admin: `admin@system.local` / `admin123`
- User: `user@system.local` / `user123`
- OAuth2 Client: `webclient` / `secret`

### 4. Create Application Database Users

For production, create dedicated users for each service:

```sql
-- Connect to RDS
psql -h your-rds-endpoint -U postgres -d postgres

-- Create service users
CREATE USER onboarding_user WITH PASSWORD 'secure_password';
CREATE USER chat_user WITH PASSWORD 'secure_password';
CREATE USER comm_user WITH PASSWORD 'secure_password';
CREATE USER workflow_user WITH PASSWORD 'secure_password';
CREATE USER billing_user WITH PASSWORD 'secure_password';
CREATE USER quality_user WITH PASSWORD 'secure_password';
CREATE USER auth_user WITH PASSWORD 'secure_password';

-- Grant privileges on databases
GRANT ALL PRIVILEGES ON DATABASE onboard_db TO onboarding_user;
GRANT ALL PRIVILEGES ON DATABASE chatbot_db TO chat_user;
GRANT ALL PRIVILEGES ON DATABASE vector_db TO onboarding_user, chat_user;
GRANT ALL PRIVILEGES ON DATABASE communications_db TO comm_user;
GRANT ALL PRIVILEGES ON DATABASE workflow_db TO workflow_user;
GRANT ALL PRIVILEGES ON DATABASE billing_db TO billing_user;
GRANT ALL PRIVILEGES ON DATABASE answer_quality_db TO quality_user;
GRANT ALL PRIVILEGES ON DATABASE authorization_db TO auth_user;

-- Grant schema privileges
\c vector_db
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA vectors TO onboarding_user, chat_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA vectors TO onboarding_user, chat_user;

-- Grant table privileges on authorization_db
\c authorization_db
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO auth_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO auth_user;
```

Update `.env` files with service-specific users.

### 5. Set Up Monitoring

#### CloudWatch Alarms

```bash
# CPU Utilization
aws cloudwatch put-metric-alarm \
  --alarm-name factorialbot-rds-cpu-high \
  --alarm-description "Alert when CPU exceeds 80%" \
  --metric-name CPUUtilization \
  --namespace AWS/RDS \
  --statistic Average \
  --period 300 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=DBInstanceIdentifier,Value=factorialbot-prod \
  --evaluation-periods 2 \
  --alarm-actions <SNS-topic-ARN>

# Free Storage Space
aws cloudwatch put-metric-alarm \
  --alarm-name factorialbot-rds-storage-low \
  --alarm-description "Alert when storage < 20%" \
  --metric-name FreeStorageSpace \
  --namespace AWS/RDS \
  --statistic Average \
  --period 300 \
  --threshold 20000000000 \
  --comparison-operator LessThanThreshold \
  --dimensions Name=DBInstanceIdentifier,Value=factorialbot-prod \
  --evaluation-periods 1 \
  --alarm-actions <SNS-topic-ARN>

# Database Connections
aws cloudwatch put-metric-alarm \
  --alarm-name factorialbot-rds-connections-high \
  --alarm-description "Alert when connections > 160 (80% of max 200)" \
  --metric-name DatabaseConnections \
  --namespace AWS/RDS \
  --statistic Average \
  --period 300 \
  --threshold 160 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=DBInstanceIdentifier,Value=factorialbot-prod \
  --evaluation-periods 2 \
  --alarm-actions <SNS-topic-ARN>
```

#### Performance Insights

Enable Performance Insights for query analysis:
```bash
aws rds modify-db-instance \
  --db-instance-identifier factorialbot-prod \
  --enable-performance-insights \
  --performance-insights-retention-period 7
```

### 6. Configure Automated Backups

Verify backup configuration:
```bash
aws rds describe-db-instances \
  --db-instance-identifier factorialbot-prod \
  --query 'DBInstances[0].[BackupRetentionPeriod,PreferredBackupWindow]'
```

Test backup restore process:
```bash
# Restore to a test instance
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier factorialbot-test-restore \
  --db-snapshot-identifier rds:factorialbot-prod-2025-10-27 \
  --db-instance-class db.t3.medium
```

### 7. Optimize Vector Indexes

After data migration, rebuild vector indexes for optimal performance:

```sql
\c vector_db

-- Reindex vector embeddings
REINDEX INDEX CONCURRENTLY vectors.idx_chunks_tenant_embedding;

-- Analyze tables
ANALYZE vectors.document_chunks;
ANALYZE vectors.vector_search_indexes;

-- Check index usage
SELECT schemaname, tablename, indexname, idx_scan
FROM pg_stat_user_indexes
WHERE schemaname = 'vectors'
ORDER BY idx_scan;
```

### 8. Security Hardening

```bash
# Remove temporary security group rule (your IP)
aws ec2 revoke-security-group-ingress \
  --group-id sg-xxxxxxxx \
  --protocol tcp \
  --port 5432 \
  --cidr <your-ip>/32

# Require SSL connections
aws rds modify-db-instance \
  --db-instance-identifier factorialbot-prod \
  --cloudwatch-logs-export-configuration '{"LogTypesToEnable":["postgresql"]}'

# Update parameter group to require SSL
aws rds modify-db-parameter-group \
  --db-parameter-group-name factorialbot-params \
  --parameters "ParameterName=rds.force_ssl,ParameterValue=1,ApplyMethod=immediate"
```

Update connection strings to use SSL:
```env
# Python services
DATABASE_URL=postgresql://user:password@your-rds-endpoint:5432/onboard_db?sslmode=require

# Spring Boot (authorization-server)
spring.datasource.url=jdbc:postgresql://your-rds-endpoint:5432/authorization_db?sslmode=require
```

**IMPORTANT: Change Default Credentials**

The authorization server includes default test credentials that **MUST** be changed in production:

```sql
\c authorization_db

-- Update admin password (use BCrypt hash)
UPDATE users SET password = '{bcrypt}$2a$10$YOUR_NEW_BCRYPT_HASH'
WHERE username = 'admin';

-- Update OAuth2 client secret (use BCrypt hash)
UPDATE registered_clients SET client_secret = '{bcrypt}$2a$10$YOUR_NEW_BCRYPT_HASH'
WHERE client_id = 'webclient';

-- Or delete default users and create new ones
DELETE FROM users WHERE username IN ('admin', 'user');
```

---

## Rollback Plan

### Scenario 1: Migration Fails During Schema Creation

**Action:** Simply re-run schema scripts (idempotent with `IF NOT EXISTS`)

```bash
# Drop and recreate if needed
psql -h your-rds-endpoint -U postgres -d postgres -c "DROP DATABASE vector_db"

# Re-run initialization
psql -h your-rds-endpoint -U postgres -d postgres -f 01-initialization/001-create-databases-and-extensions.sql
```

### Scenario 2: Migration Fails During Data Transfer

**Action:** Truncate imported data and retry

```bash
# Connect to specific database
psql -h your-rds-endpoint -U postgres -d onboard_db

# Truncate all tables (preserves schema)
TRUNCATE TABLE documents CASCADE;
TRUNCATE TABLE subscriptions CASCADE;
-- ... etc

# Or truncate all tables in schema
DO $$ DECLARE
  r RECORD;
BEGIN
  FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
    EXECUTE 'TRUNCATE TABLE ' || quote_ident(r.tablename) || ' CASCADE';
  END LOOP;
END $$;

# Re-run data migration
cd 04-data-migration
./migrate-data.sh
```

### Scenario 3: Application Fails After Migration

**Action:** Switch back to Docker PostgreSQL

```bash
# Update .env files to point back to Docker
DATABASE_URL=postgresql://postgres:password@localhost:5432/onboard_db

# Restart services
docker-compose restart postgres
cd onboarding-service && uvicorn app.main:app --reload
```

### Scenario 4: Data Corruption Detected

**Action:** Restore from RDS automated backup

```bash
# List available backups
aws rds describe-db-snapshots \
  --db-instance-identifier factorialbot-prod \
  --snapshot-type automated

# Restore to point in time (before corruption)
aws rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier factorialbot-prod \
  --target-db-instance-identifier factorialbot-prod-restored \
  --restore-time 2025-10-27T10:00:00Z

# Verify restored instance
psql -h factorialbot-prod-restored.xxx.rds.amazonaws.com -U postgres -d onboard_db

# If verified, rename instances
aws rds modify-db-instance \
  --db-instance-identifier factorialbot-prod \
  --new-db-instance-identifier factorialbot-prod-corrupted \
  --apply-immediately

aws rds modify-db-instance \
  --db-instance-identifier factorialbot-prod-restored \
  --new-db-instance-identifier factorialbot-prod \
  --apply-immediately
```

### Scenario 5: Complete Rollback Required

**Action:** Restore from pre-migration Docker backup

```bash
# Stop all services
docker-compose down

# Restore Docker PostgreSQL data
docker-compose up -d postgres
docker-compose exec -T postgres psql -U postgres < full_backup.sql

# Verify data
docker-compose exec postgres psql -U postgres -d onboard_db -c "SELECT COUNT(*) FROM tenants"

# Restart services
docker-compose up -d
```

---

## Troubleshooting

### Common Issues and Solutions

#### Issue: Cannot connect to RDS

**Symptoms:** `Connection refused` or timeout errors

**Solutions:**
```bash
# Check security group
aws ec2 describe-security-groups --group-ids sg-xxxxxxxx

# Verify RDS is available
aws rds describe-db-instances \
  --db-instance-identifier factorialbot-prod \
  --query 'DBInstances[0].DBInstanceStatus'

# Test from EC2 instance in same VPC
ssh ec2-instance
psql -h rds-endpoint -U postgres -d postgres

# Check DNS resolution
nslookup your-rds-endpoint

# Verify RDS is not in private subnet without NAT
```

#### Issue: pgvector extension not available

**Symptoms:** `ERROR: extension "vector" is not available`

**Solutions:**
```bash
# Check PostgreSQL version (needs 11.1+)
psql -h rds-endpoint -U postgres -c "SELECT version()"

# For PostgreSQL < 15, may need manual installation
# Upgrade to PostgreSQL 15+ for native pgvector support

# Verify extension files exist
psql -h rds-endpoint -U postgres -c "SELECT * FROM pg_available_extensions WHERE name='vector'"
```

#### Issue: Data import fails with constraint violations

**Symptoms:** `ERROR: duplicate key value violates unique constraint`

**Solutions:**
```sql
-- Disable triggers during import
SET session_replication_role = replica;

-- Import data
\i data.sql

-- Re-enable triggers
SET session_replication_role = default;

-- Reset sequences
SELECT setval('sequence_name', (SELECT MAX(id) FROM table_name));
```

#### Issue: Flyway migration conflicts (authorization_db)

**Symptoms:** Spring Boot tries to re-run migrations V1-V9

**Solutions:**
```sql
-- Verify Flyway history exists
\c authorization_db
SELECT version, description, success FROM flyway_schema_history ORDER BY installed_rank;

-- If missing, manually add baseline entry
INSERT INTO flyway_schema_history (
    installed_rank, version, description, type, script,
    checksum, installed_by, execution_time, success
) VALUES (
    1, '9', 'Consolidated RDS migration V1-V9', 'SQL',
    '008-authorization-server-schema.sql',
    0, 'rds-migration', 0, true
);
```

Configure Spring Boot to use baseline:
```properties
spring.flyway.baseline-on-migrate=true
spring.flyway.baseline-version=9
```

#### Issue: Slow vector similarity search

**Symptoms:** Query timeout or >5 second response times

**Solutions:**
```sql
-- Check if IVFFlat index exists
SELECT indexname FROM pg_indexes
WHERE schemaname = 'vectors' AND indexname = 'idx_chunks_tenant_embedding';

-- Rebuild index with more lists for large datasets
DROP INDEX vectors.idx_chunks_tenant_embedding;
CREATE INDEX idx_chunks_tenant_embedding ON vectors.document_chunks
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 1000);  -- Increase from 100 for >100K vectors

-- Update statistics
ANALYZE vectors.document_chunks;

-- Check query plan
EXPLAIN ANALYZE
SELECT id, content, embedding <=> query_vector as distance
FROM vectors.document_chunks
WHERE tenant_id = 'xxx'
ORDER BY embedding <=> query_vector
LIMIT 10;
```

#### Issue: Out of memory errors during migration

**Symptoms:** `ERROR: out of memory`

**Solutions:**
```bash
# Reduce batch size in data import
pg_dump --data-only --inserts --rows-per-insert=1000

# Increase RDS instance size temporarily
aws rds modify-db-instance \
  --db-instance-identifier factorialbot-prod \
  --db-instance-class db.m5.large \
  --apply-immediately

# After migration, scale back down
aws rds modify-db-instance \
  --db-instance-identifier factorialbot-prod \
  --db-instance-class db.t3.medium
```

#### Issue: Connection pool exhausted

**Symptoms:** `FATAL: sorry, too many clients already`

**Solutions:**
```sql
-- Check current connections
SELECT COUNT(*) FROM pg_stat_activity;

-- Check max connections
SHOW max_connections;

-- Identify idle connections
SELECT pid, usename, application_name, state, state_change
FROM pg_stat_activity
WHERE state = 'idle'
ORDER BY state_change;

-- Terminate idle connections (if safe)
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state = 'idle' AND state_change < now() - interval '10 minutes';

-- Increase max_connections in parameter group
# Update parameter group:
max_connections = 300
```

Configure connection pooling in application:
```python
# SQLAlchemy example
engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600
)
```

---

## Performance Tuning

### Database-Level Optimization

```sql
-- Regular maintenance (schedule weekly)
VACUUM ANALYZE vectors.document_chunks;
VACUUM ANALYZE chat_messages;

-- Identify slow queries
SELECT
    query,
    calls,
    total_exec_time,
    mean_exec_time,
    max_exec_time
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;

-- Check index usage
SELECT
    schemaname,
    tablename,
    indexname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE idx_scan = 0 AND indexname NOT LIKE 'pg_%'
ORDER BY pg_relation_size(indexrelid) DESC;

-- Remove unused indexes
DROP INDEX IF EXISTS unused_index_name;
```

### RDS-Level Optimization

```bash
# Enable Performance Insights
aws rds modify-db-instance \
  --db-instance-identifier factorialbot-prod \
  --enable-performance-insights \
  --performance-insights-retention-period 7

# Configure parameter group for performance
aws rds modify-db-parameter-group \
  --db-parameter-group-name factorialbot-params \
  --parameters \
    "ParameterName=shared_buffers,ParameterValue={DBInstanceClassMemory/4},ApplyMethod=pending-reboot" \
    "ParameterName=effective_cache_size,ParameterValue={DBInstanceClassMemory*3/4},ApplyMethod=immediate" \
    "ParameterName=random_page_cost,ParameterValue=1.1,ApplyMethod=immediate" \
    "ParameterName=effective_io_concurrency,ParameterValue=200,ApplyMethod=immediate"

# Enable query logging for slow queries
aws rds modify-db-parameter-group \
  --db-parameter-group-name factorialbot-params \
  --parameters \
    "ParameterName=log_min_duration_statement,ParameterValue=1000,ApplyMethod=immediate" \
    "ParameterName=log_statement,ParameterValue=ddl,ApplyMethod=immediate"

# Monitor logs
aws rds download-db-log-file-portion \
  --db-instance-identifier factorialbot-prod \
  --log-file-name error/postgresql.log.2025-10-27-12 \
  --output text
```

### Application-Level Optimization

```python
# Use connection pooling
from sqlalchemy.pool import QueuePool

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=20,
    max_overflow=30,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo_pool=True
)

# Optimize vector queries
async def search_vectors(tenant_id: str, query_embedding: list, limit: int = 10):
    """Optimized vector search with tenant filtering"""
    query = """
    SELECT id, content, source_name,
           embedding <=> :query_embedding as distance
    FROM vectors.document_chunks
    WHERE tenant_id = :tenant_id
      AND embedding IS NOT NULL
    ORDER BY embedding <=> :query_embedding
    LIMIT :limit
    """
    # Use prepared statements
    result = await db.execute(
        text(query),
        {
            "tenant_id": tenant_id,
            "query_embedding": query_embedding,
            "limit": limit
        }
    )
    return result.fetchall()

# Implement caching for frequent queries
from functools import lru_cache

@lru_cache(maxsize=1000)
def get_plan_by_id(plan_id: str):
    return db.query(Plan).filter(Plan.id == plan_id).first()
```

---

## Cost Optimization

### Monitor Costs

```bash
# Get RDS cost estimate
aws ce get-cost-and-usage \
  --time-period Start=2025-10-01,End=2025-10-31 \
  --granularity MONTHLY \
  --metrics "UnblendedCost" \
  --filter file://rds-filter.json

# rds-filter.json
{
  "Dimensions": {
    "Key": "SERVICE",
    "Values": ["Amazon Relational Database Service"]
  }
}
```

### Cost Optimization Tips

1. **Right-size Instance:**
   - Start with t3.medium, monitor CPU/memory
   - Scale up only if sustained >70% utilization
   - Use Reserved Instances for 40-60% savings

2. **Storage Optimization:**
   - Enable storage autoscaling
   - Use GP3 instead of IO1 (20% cheaper)
   - Archive old data to S3

3. **Backup Optimization:**
   - 7-day retention (vs 35 days)
   - Use snapshots for long-term backups
   - Delete old manual snapshots

4. **Network:**
   - Use VPC endpoints to avoid data transfer charges
   - Place RDS in same AZ as EC2 for lower latency and cost

---

## Support and Resources

### AWS Documentation
- [RDS PostgreSQL Guide](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_PostgreSQL.html)
- [pgvector on RDS](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Appendix.PostgreSQL.CommonDBATasks.Extensions.html#Appendix.PostgreSQL.CommonDBATasks.pgvector)
- [RDS Best Practices](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_BestPractices.html)

### Migration Logs

All logs stored in `rds-migration/logs/`:
- `migration_YYYYMMDD_HHMMSS.log` - Complete migration log
- `01_create_databases_YYYYMMDD_HHMMSS.log` - Database creation
- `02_schemas_YYYYMMDD_HHMMSS.log` - Schema creation
- `03_alembic_SERVICE_YYYYMMDD_HHMMSS.log` - Alembic migrations per service
- `validation_YYYYMMDD_HHMMSS.log` - Validation results

### Contacts

For issues during migration:
- Review logs in `rds-migration/logs/`
- Check AWS RDS events in console
- Monitor CloudWatch metrics
- Review Performance Insights

---

## Summary Checklist

**Before Migration:**
- [ ] RDS instance created and configured
- [ ] Security groups configured
- [ ] Backup of Docker PostgreSQL completed
- [ ] Migration scripts tested in staging
- [ ] Stakeholders notified

**During Migration:**
- [ ] Databases created successfully
- [ ] Schemas created successfully
- [ ] Alembic migrations completed
- [ ] Data migrated successfully
- [ ] Validation checks passed

**After Migration:**
- [ ] Application .env files updated
- [ ] Services tested with RDS
- [ ] Application users created
- [ ] CloudWatch alarms configured
- [ ] Automated backups verified
- [ ] Performance optimized
- [ ] Documentation updated

**Migration Complete!** 🎉

Your FactorialBot platform is now running on AWS RDS with improved:
- **Reliability:** Multi-AZ deployment, automated backups
- **Scalability:** Easy vertical/horizontal scaling
- **Performance:** Optimized storage, monitoring
- **Security:** Encryption at rest and in transit
- **Maintainability:** Automated patching, monitoring

## Additional Notes

### Authorization Server (Spring Boot + Flyway)

The authorization server uses a different migration approach than the Python services:

**Migration Type:** Flyway (not Alembic)
**Original Migrations:** V1-V9 (consolidated into single script)
**Schema Script:** `02-schemas/008-authorization-server-schema.sql`

**Key Tables:**
- `tenants` - Organization data with API keys and subscription tracking
- `users` - User accounts with email verification
- `roles` - RBAC roles (ADMIN, USER, TENANT_ADMIN)
- `user_roles` - User-role assignments
- `registered_clients` - OAuth2 client configurations
- `tenant_settings` - Branding customization (colors, logos, widget text)
- `verification_tokens` - Email verification and password reset

**Default Data:**
- 3 roles (ADMIN, USER, TENANT_ADMIN)
- 2 users (admin, user) with default passwords
- 1 OAuth2 client (webclient) for all authentication flows

**Post-Migration:**
1. Spring Boot will detect `flyway_schema_history` table
2. Recognize version 9 as current baseline
3. Only run new migrations (V10+) if added in the future

**Security Notice:**
- Default passwords are `{noop}admin123` and `{noop}user123`
- OAuth2 client secret is BCrypt hashed
- **Change all default credentials before production deployment**

For more details, see comments in `02-schemas/008-authorization-server-schema.sql`