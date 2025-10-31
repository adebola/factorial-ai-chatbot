# Alembic Migrations for RDS

This directory contains instructions for running Alembic migrations on RDS after the base schema has been created.

## Overview

The base schemas in `02-schemas/` create the fundamental table structures. However, each service uses Alembic for managing schema evolution. After running the base schema scripts, you must run Alembic migrations for each service to ensure all columns, constraints, and recent schema changes are applied.

## Services with Alembic Migrations

### 1. Communications Service (communications_db)
**Location:** `backend/communications-service/alembic/`

**Migrations:**
- `001` - Initial migration (creates base tables)
- `5f3e22e53553` - Add missing columns (retry_count, last_retry_at, updated_at)

**How to Run:**
```bash
cd backend/communications-service

# Update DATABASE_URL in .env to point to RDS
DATABASE_URL=postgresql://user:password@your-rds-endpoint:5432/communications_db

# Run migrations
alembic upgrade head

# Verify
alembic current
```

### 2. Workflow Service (workflow_db)
**Location:** `backend/workflow-service/alembic/`

**Migrations:**
- `2a45ef8b095f` - Initial tables (workflows, executions, states, templates)
- `8b526191b098` - Add lowercase trigger_type enum values
- `3b4c5d6e7f8a` - Create workflow_action_data table

**How to Run:**
```bash
cd backend/workflow-service

# Update DATABASE_URL in .env
DATABASE_URL=postgresql://user:password@your-rds-endpoint:5432/workflow_db

# Run migrations
alembic upgrade head

# Verify
alembic current
```

### 3. Billing Service (billing_db)
**Location:** `backend/billing-service/alembic/`

**Migrations:**
- `336adf455524` - Add new plan columns (max_document_size_mb, feature flags)
- `2d86d4df8676` - Seed default plans (Basic, Lite, Pro, Enterprise)
- `3f8e9d2a1b5c` - Add pending plan fields for subscription changes

**How to Run:**
```bash
cd backend/billing-service

# Update DATABASE_URL in .env
DATABASE_URL=postgresql://user:password@your-rds-endpoint:5432/billing_db

# Run migrations
alembic upgrade head

# Verify
alembic current
```

### 4. Answer Quality Service (answer_quality_db)
**Location:** `backend/answer-quality-service/alembic/`

**Migrations:**
- `2ce92ea51ef5` - Initial migration (feedback, metrics, session_quality, knowledge_gaps)
- `17d05ab982ab` - Add alert system tables (alert_rules, alert_history, job_execution_logs)

**How to Run:**
```bash
cd backend/answer-quality-service

# Update DATABASE_URL in .env
DATABASE_URL=postgresql://user:password@your-rds-endpoint:5432/answer_quality_db

# Run migrations
alembic upgrade head

# Verify
alembic current
```

### 5. Onboarding Service (onboard_db)
**Location:** `backend/onboarding-service/alembic/`

**Note:** This service has extensive Alembic migrations for:
- Tenant and user models
- Document categorization
- Subscription management
- Payment integration
- Usage tracking

**How to Run:**
```bash
cd backend/onboarding-service

# Update DATABASE_URL in .env
DATABASE_URL=postgresql://user:password@your-rds-endpoint:5432/onboard_db

# Run migrations
alembic upgrade head

# Verify
alembic current
```

### 6. Chat Service (chatbot_db)
**Location:** `backend/chat-service/alembic/`

**Note:** Chat service may have Alembic migrations for session and message schema changes.

**How to Run:**
```bash
cd backend/chat-service

# Update DATABASE_URL in .env
DATABASE_URL=postgresql://user:password@your-rds-endpoint:5432/chatbot_db

# Run migrations (if migrations exist)
alembic upgrade head

# Verify
alembic current
```

## Migration Execution Order

Run migrations in this order to handle any cross-database dependencies:

1. **billing_db** - Plan definitions needed by other services
2. **onboard_db** - Core tenant and subscription models
3. **chatbot_db** - Chat session management
4. **communications_db** - Email/SMS delivery
5. **workflow_db** - Workflow engine
6. **answer_quality_db** - Quality monitoring

## Troubleshooting

### Migration Already Applied
If you see "Target database is not up to date", the base schema may have already created some tables. This is expected. Alembic will skip tables that already exist.

### Enum Type Conflicts
If you get errors about enum types already existing:
```sql
-- Connect to the database
\c database_name

-- Check existing enums
SELECT typname FROM pg_type WHERE typtype = 'e';

-- If needed, drop and recreate
DROP TYPE enum_name CASCADE;
-- Then re-run migration
```

### Connection Issues
Ensure your RDS security group allows connections from your IP:
```bash
# Test connection
psql postgresql://user:password@your-rds-endpoint:5432/database_name -c "SELECT 1"
```

### Missing Dependencies
Ensure all Python dependencies are installed:
```bash
pip install alembic psycopg2-binary sqlalchemy
```

## Verification

After running all migrations, verify the schema:

```bash
# For each database
psql postgresql://user:password@your-rds-endpoint:5432/database_name

# Check tables
\dt

# Check columns for a specific table
\d table_name

# Check alembic version
SELECT * FROM alembic_version;
```

## Important Notes

1. **Idempotency:** Base schema scripts use `IF NOT EXISTS` clauses, so running them multiple times is safe.

2. **Alembic State:** Alembic tracks applied migrations in the `alembic_version` table. Do not manually modify this table.

3. **Conflicts:** If base schema and Alembic try to create the same table, Alembic will fail. This is expected - simply skip that migration or modify it.

4. **Backup First:** Always backup your database before running migrations in production:
```bash
pg_dump -h your-rds-endpoint -U user database_name > backup.sql
```

5. **Staging Environment:** Test all migrations in a staging RDS instance before running in production.

## Rollback

To rollback a migration:
```bash
# Rollback one migration
alembic downgrade -1

# Rollback to specific version
alembic downgrade <revision_id>

# Rollback all migrations
alembic downgrade base
```

## Post-Migration Tasks

After running all Alembic migrations:

1. **Update Connection Strings:** Ensure all services point to RDS in their .env files
2. **Test Services:** Start each service and verify database connectivity
3. **Run Data Migration:** Execute data migration scripts if migrating from existing Docker database
4. **Verify Indexes:** Check that all indexes were created successfully
5. **Monitor Performance:** Watch RDS metrics during initial load

## Getting Help

If migrations fail:
1. Check the Alembic migration file for the failing revision
2. Review the error message carefully
3. Check if the issue is due to base schema pre-creating tables
4. Manually apply the migration SQL if needed
5. Update alembic_version table to mark migration as applied