# RDS Migration Quick Start Guide

## TL;DR - Fastest Path to Migration

### Prerequisites
```bash
# Ensure you have:
# 1. AWS RDS PostgreSQL instance running (PostgreSQL 15+)
# 2. RDS endpoint and credentials
# 3. Docker PostgreSQL accessible (if migrating data)
# 4. psql and pg_dump installed
```

### One-Command Migration

```bash
# Set your RDS credentials
export RDS_ENDPOINT=your-instance.region.rds.amazonaws.com
export RDS_PORT=5432
export RDS_MASTER_USER=postgres
export RDS_MASTER_PASSWORD=your-secure-password

# Run migration
cd rds-migration/scripts
./run-migration.sh
```

That's it! The script will:
- Create 8 databases
- Create all schemas and tables
- Run Alembic migrations
- Optionally migrate data from Docker
- Validate everything
- Generate updated .env files

**Estimated Time:** 2-6 hours (depending on data size)

---

## Manual Migration (Step-by-Step)

### Step 1: Create Databases (5 minutes)
```bash
cd rds-migration
export PGPASSWORD=your-rds-password

psql -h your-rds-endpoint -U postgres -d postgres \
  -f 01-initialization/001-create-databases-and-extensions.sql
```

### Step 2: Create Schemas (10 minutes)
```bash
for file in 02-schemas/*.sql; do
  psql -h your-rds-endpoint -U postgres -f "$file"
done
```

### Step 3: Run Alembic Migrations (15 minutes)
```bash
# For each service:
cd ../communications-service
export DATABASE_URL=postgresql://postgres:password@your-rds-endpoint:5432/communications_db
alembic upgrade head

# Repeat for: billing-service, workflow-service, answer-quality-service, onboarding-service
```

### Step 4: Migrate Data (30 minutes - 4 hours)
```bash
cd rds-migration/04-data-migration

export SOURCE_HOST=localhost
export SOURCE_PASSWORD=password
export TARGET_HOST=your-rds-endpoint
export TARGET_PASSWORD=your-rds-password

./migrate-data.sh
```

### Step 5: Validate (2 minutes)
```bash
cd ../05-validation
export RDS_HOST=your-rds-endpoint
export RDS_PASSWORD=your-rds-password

./validate.sh
```

### Step 6: Update Application Config
```bash
# Update all service .env files:
DATABASE_URL=postgresql://user:password@your-rds-endpoint:5432/onboard_db
VECTOR_DATABASE_URL=postgresql://user:password@your-rds-endpoint:5432/vector_db

# Test services
cd onboarding-service && uvicorn app.main:app --reload
```

---

## Common Commands

### Check Migration Status
```bash
# List all databases
psql -h your-rds-endpoint -U postgres -d postgres \
  -c "SELECT datname FROM pg_database WHERE datname LIKE '%_db'"

# Check table counts
psql -h your-rds-endpoint -U postgres -d vector_db \
  -c "SELECT COUNT(*) FROM vectors.document_chunks"

# Verify Alembic version
psql -h your-rds-endpoint -U postgres -d communications_db \
  -c "SELECT version_num FROM alembic_version"
```

### Test Connectivity
```bash
# Test RDS connection
psql -h your-rds-endpoint -U postgres -d postgres -c "SELECT version()"

# Test from Python
python3 -c "
from sqlalchemy import create_engine
engine = create_engine('postgresql://postgres:password@your-rds-endpoint:5432/postgres')
conn = engine.connect()
result = conn.execute('SELECT 1')
print('✓ Connection successful')
conn.close()
"
```

### Rollback
```bash
# If migration fails, truncate and retry:
psql -h your-rds-endpoint -U postgres -d onboard_db

# Truncate all tables
DO $$ DECLARE
  r RECORD;
BEGIN
  FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
    EXECUTE 'TRUNCATE TABLE ' || quote_ident(r.tablename) || ' CASCADE';
  END LOOP;
END $$;

# Re-run data migration
cd 04-data-migration && ./migrate-data.sh
```

---

## Troubleshooting

### Cannot connect to RDS
```bash
# Check security group allows your IP
aws ec2 describe-security-groups --group-ids sg-xxxxxxxx

# Test connection
telnet your-rds-endpoint 5432
```

### pgvector not available
```bash
# Verify PostgreSQL version (need 15+)
psql -h your-rds-endpoint -U postgres -c "SELECT version()"

# Check extension
psql -h your-rds-endpoint -U postgres -d vector_db \
  -c "SELECT * FROM pg_available_extensions WHERE name='vector'"
```

### Data import fails
```bash
# Check logs
cat rds-migration/04-data-migration/backups/*/migration.log

# Check row counts
diff backups/*/onboard_db_source_counts.txt \
     backups/*/onboard_db_target_counts.txt
```

### Slow vector search
```sql
-- Rebuild vector index
\c vector_db
REINDEX INDEX CONCURRENTLY vectors.idx_chunks_tenant_embedding;
ANALYZE vectors.document_chunks;
```

---

## After Migration

1. **Update .env files** with RDS connection strings
2. **Test all services** with RDS connectivity
3. **Enable CloudWatch alarms** for monitoring
4. **Configure automated backups** (7+ day retention)
5. **Remove migration security group rules** (your IP)
6. **Document RDS endpoint** for team

---

## Important Files

- **Complete Guide:** `README.md`
- **Validation Results:** `05-validation/validation_*.log`
- **Migration Logs:** `logs/migration_*.log`
- **Data Backups:** `04-data-migration/backups/`
- **Environment Template:** `scripts/env_template.txt`

---

## Need Help?

1. Check `README.md` for detailed documentation
2. Review logs in `logs/` directory
3. Run validation: `cd 05-validation && ./validate.sh`
4. Check AWS RDS events in console
5. Review CloudWatch metrics and Performance Insights

---

## Migration Checklist

**Before:**
- [ ] RDS instance created
- [ ] Security group configured
- [ ] Docker backup completed

**During:**
- [ ] Databases created
- [ ] Schemas created
- [ ] Alembic migrations run
- [ ] Data migrated
- [ ] Validation passed

**After:**
- [ ] Services tested
- [ ] Monitoring enabled
- [ ] Backups verified
- [ ] Team notified

**Done!** Your database is now on RDS. 🚀