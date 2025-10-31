# Data Migration from Docker to RDS

This directory contains scripts for migrating data from your Docker PostgreSQL instance to AWS RDS.

## Prerequisites

1. **Source Database Running:** Your Docker PostgreSQL must be running and accessible
2. **Target Schema Created:** RDS databases must exist with all schemas created (run `02-schemas/` scripts first)
3. **Network Connectivity:** Your machine must be able to connect to both source and target databases
4. **Sufficient Disk Space:** At least 10GB free space for temporary dump files
5. **psql and pg_dump Installed:** PostgreSQL client tools must be available

## Migration Script

The main migration script is `migrate-data.sh`.

### Configuration

Set these environment variables before running:

```bash
# Source (Docker PostgreSQL)
export SOURCE_HOST=localhost
export SOURCE_PORT=5432
export SOURCE_USER=postgres
export SOURCE_PASSWORD=password

# Target (AWS RDS)
export TARGET_HOST=your-rds-endpoint.region.rds.amazonaws.com
export TARGET_PORT=5432
export TARGET_USER=postgres
export TARGET_PASSWORD=your-rds-password
```

### Running the Migration

```bash
# Set environment variables
export SOURCE_HOST=localhost
export SOURCE_PORT=5432
export SOURCE_USER=postgres
export SOURCE_PASSWORD=password
export TARGET_HOST=factorialbot-prod.abcdefgh.us-east-1.rds.amazonaws.com
export TARGET_PORT=5432
export TARGET_USER=postgres
export TARGET_PASSWORD=your-secure-password

# Run migration
./migrate-data.sh
```

### What the Script Does

For each database, the script:

1. **Verifies Connectivity:** Checks both source and target are accessible
2. **Checks Disk Space:** Ensures sufficient space for dump files
3. **Dumps Data:** Exports data-only dump from source (schema excluded)
4. **Records Row Counts:** Saves source table row counts for verification
5. **Disables Triggers:** Temporarily disables triggers on target for faster import
6. **Imports Data:** Loads data into target RDS database
7. **Re-enables Triggers:** Restores trigger functionality
8. **Updates Sequences:** Resets sequence counters to match imported data
9. **Analyzes Tables:** Updates statistics for query optimizer
10. **Verifies Counts:** Compares row counts between source and target

## Migration Order

Databases are migrated in this order to handle dependencies:

1. `billing_db` - Plan definitions
2. `onboard_db` - Tenants, users, subscriptions
3. `chatbot_db` - Chat sessions and messages
4. `vector_db` - Document embeddings
5. `communications_db` - Email/SMS messages
6. `workflow_db` - Workflow definitions and executions
7. `answer_quality_db` - Quality metrics and feedback

## Output Files

The script creates a timestamped backup directory with:

```
backups/YYYYMMDD_HHMMSS/
├── migration.log                    # Complete migration log
├── vector_db_data.sql              # Data dumps
├── chatbot_db_data.sql
├── onboard_db_data.sql
├── ...
├── vector_db_source_counts.txt     # Row counts from source
├── vector_db_target_counts.txt     # Row counts from target
├── vector_db_import.log            # Import logs
└── ...
```

## Verification

After migration completes:

### 1. Review Logs
```bash
# Check migration log
cat backups/YYYYMMDD_HHMMSS/migration.log

# Check for errors in import logs
grep -i error backups/YYYYMMDD_HHMMSS/*_import.log
```

### 2. Compare Row Counts
```bash
# The script automatically compares row counts
# Review the output in migration.log

# Or manually check
cat backups/YYYYMMDD_HHMMSS/onboard_db_source_counts.txt
cat backups/YYYYMMDD_HHMMSS/onboard_db_target_counts.txt
```

### 3. Verify Data Integrity
```bash
# Connect to RDS
psql -h your-rds-endpoint -U postgres -d onboard_db

-- Check critical tables
SELECT COUNT(*) FROM tenants;
SELECT COUNT(*) FROM documents;
SELECT COUNT(*) FROM subscriptions;

-- Check recent records
SELECT * FROM tenants ORDER BY created_at DESC LIMIT 5;
```

### 4. Verify Vector Embeddings
```bash
# Connect to vector database
psql -h your-rds-endpoint -U postgres -d vector_db

-- Check embeddings
SELECT COUNT(*) FROM vectors.document_chunks;

-- Verify embedding dimensions
SELECT vector_dims(embedding) FROM vectors.document_chunks LIMIT 1;
-- Should return: 1536

-- Test vector similarity search
SELECT id, content, embedding <=> array_fill(0.0::real, ARRAY[1536])::vector as distance
FROM vectors.document_chunks
LIMIT 5;
```

## Troubleshooting

### Connection Refused
```bash
# Check RDS security group allows your IP
aws ec2 describe-security-groups --group-ids sg-xxxxxx

# Test connectivity
psql -h your-rds-endpoint -U postgres -d postgres -c "SELECT 1"
```

### Insufficient Disk Space
```bash
# Check available space
df -h

# Clean up old backups
rm -rf backups/old_backup_folder
```

### Permission Errors
```bash
# Ensure target user has necessary privileges
psql -h your-rds-endpoint -U postgres -d postgres

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE vector_db TO your_app_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA vectors TO your_app_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA vectors TO your_app_user;
```

### Trigger Issues
If triggers cause problems during import:
```sql
-- Manually disable triggers
SET session_replication_role = replica;

-- Run your import
\i data.sql

-- Re-enable triggers
SET session_replication_role = default;
```

### Sequence Out of Sync
If you get duplicate key errors after migration:
```sql
-- Reset all sequences in a database
SELECT 'SELECT SETVAL(' ||
       quote_literal(quote_ident(schemaname) || '.' || quote_ident(sequencename)) ||
       ', COALESCE(MAX(' || quote_ident(attname) || '), 1)) FROM ' ||
       quote_ident(schemaname) || '.' || quote_ident(tablename) || ';'
FROM pg_sequences
JOIN pg_class ON pg_class.oid = pg_sequences.schemaname::regnamespace
JOIN pg_attribute ON pg_attribute.attrelid = pg_class.oid;
```

### Foreign Key Violations
If you see foreign key violations:
```bash
# Dump with data in proper order (topological sort)
pg_dump -h localhost -U postgres -d onboard_db \
  --data-only \
  --no-owner \
  --disable-triggers \
  --section=data \
  -f onboard_db_ordered.sql
```

## Performance Optimization

### For Large Databases (> 100GB)

1. **Use pg_dump with compression:**
```bash
pg_dump -h localhost -U postgres -d onboard_db \
  --data-only -Fc -f onboard_db_data.dump

# Restore with parallel jobs
pg_restore -h your-rds-endpoint -U postgres -d onboard_db \
  -j 4 onboard_db_data.dump
```

2. **Temporarily increase RDS resources:**
   - Scale up instance class before migration
   - Increase storage IOPS
   - Scale back down after migration

3. **Disable autovacuum during import:**
```sql
ALTER TABLE table_name SET (autovacuum_enabled = false);
-- Import data
ALTER TABLE table_name SET (autovacuum_enabled = true);
VACUUM ANALYZE table_name;
```

4. **Drop indexes before import, recreate after:**
```sql
-- Get index definitions
SELECT indexdef FROM pg_indexes WHERE tablename = 'document_chunks';

-- Drop indexes
DROP INDEX idx_name;

-- Import data

-- Recreate indexes (potentially faster on populated table)
CREATE INDEX CONCURRENTLY idx_name ON table_name(column);
```

## Rollback

If migration fails and you need to rollback:

### 1. Truncate Imported Data
```sql
-- Connect to RDS
psql -h your-rds-endpoint -U postgres -d onboard_db

-- Truncate tables (preserves schema)
TRUNCATE TABLE table_name CASCADE;
```

### 2. Re-run Migration
```bash
# Fix any issues
# Re-run migration script
./migrate-data.sh
```

### 3. Restore from Backup
```bash
# Restore RDS from automated backup
aws rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier factorialbot-prod \
  --target-db-instance-identifier factorialbot-prod-restored \
  --restore-time 2025-10-27T10:00:00Z
```

## Post-Migration Tasks

After successful migration:

1. **Update Application Configuration:**
```bash
# Update .env files for all services
DATABASE_URL=postgresql://user:password@rds-endpoint:5432/onboard_db
VECTOR_DATABASE_URL=postgresql://user:password@rds-endpoint:5432/vector_db
```

2. **Test All Services:**
```bash
# Start services with RDS connection
cd chat-service && uvicorn app.main:app --reload
cd onboarding-service && uvicorn app.main:app --reload
```

3. **Run Validation Script:**
```bash
cd ../05-validation
./validate.sh
```

4. **Monitor RDS Metrics:**
   - CPU utilization
   - Database connections
   - Read/Write latency
   - Free storage space

5. **Enable Automated Backups:**
```bash
aws rds modify-db-instance \
  --db-instance-identifier factorialbot-prod \
  --backup-retention-period 7 \
  --preferred-backup-window "03:00-04:00"
```

6. **Set Up Monitoring Alarms:**
   - CloudWatch alarms for CPU, connections, storage
   - Enhanced monitoring
   - Performance Insights

## Maintenance

### Regular Tasks

- **Daily:** Monitor RDS CloudWatch metrics
- **Weekly:** Check slow query logs
- **Monthly:** Review storage usage and scale if needed
- **Quarterly:** Test backup restore process

### Cleanup

After confirming successful migration (e.g., 1 week):
```bash
# Remove backup files
rm -rf backups/YYYYMMDD_HHMMSS

# Stop Docker PostgreSQL (if no longer needed)
docker-compose stop postgres
```