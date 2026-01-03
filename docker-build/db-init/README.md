# Vector Database DDL Scripts - Usage Guide

## Overview

This directory contains DDL scripts for initializing and managing the vector database schema for FactorialBot. These scripts handle the creation of tables, indexes, and schema required for vector-based document search.

## Critical Information

**Schema Used**: All application code expects tables in the `vectors` schema, NOT the `public` schema.

**Table Location**: `vectors.document_chunks` (not `public.document_chunks`)

## Scripts Execution Order

### For Fresh Database Initialization (Docker init)

When Docker initializes a new database, scripts in this directory are executed in **alphabetical order**:

1. `01-init-databases.sql` - Creates all databases (vector_db, chatbot_db, onboard_db, etc.)
2. `02-init-pgvector-schemas.sql` - Creates vectors schema and document_chunks table
3. `03-add-categorization-to-vector-db.sql` - Adds categorization columns (optional, can be skipped)
4. `04-fix-vector-db-schema.sql` - Complete schema setup (includes everything from 02 and 03)
5. `005-create-billing-database.sql` - Creates billing database

### For Existing Production Database

If your production database already exists and you're getting errors like:
```
relation "vectors.document_chunks" does not exist
```

**Run this script manually**:
```bash
PGPASSWORD=your_password psql -h your_host -U postgres -d vector_db -f 04-fix-vector-db-schema.sql
```

## Script Descriptions

### 01-init-databases.sql
- Creates all required databases
- Enables pgvector and uuid-ossp extensions
- Grants permissions to postgres user
- **When to run**: Only during initial Docker database setup

### 02-init-pgvector-schemas.sql
- Creates `vectors` schema in vector_db
- Creates `vectors.document_chunks` table with basic columns
- Creates `vectors.vector_search_indexes` table
- Creates basic indexes for performance
- **Status**: ✅ Correct - uses vectors schema

### 03-add-categorization-to-vector-db.sql
- Adds categorization columns to vectors.document_chunks
- Columns: category_ids, tag_ids, content_type
- Creates GIN indexes for array operations
- **Status**: ✅ Fixed to use vectors schema (was incorrectly using public schema)
- **When to run**: Optional, only if using categorization features

### 03-remove-categorization-from-vector-db.sql
- Removes categorization columns (rollback script)
- **Status**: ✅ Fixed to use vectors schema
- **When to run**: Only if you need to remove categorization features

### 04-fix-vector-db-schema.sql (RECOMMENDED FOR PRODUCTION)
- **Complete schema setup in one script**
- Creates vectors schema
- Creates document_chunks table with ALL columns (including categorization)
- Creates vector_search_indexes table
- Creates all indexes
- Safe to run multiple times (uses IF NOT EXISTS)
- Includes verification and status reporting
- **When to run**: On existing production databases to ensure correct schema

### 005-create-billing-database.sql
- Creates billing_db database
- **When to run**: During initial setup if billing service is used

## Common Issues and Solutions

### Issue 1: "relation 'vectors.document_chunks' does not exist"

**Cause**: The vectors schema and table haven't been created in your production database.

**Solution**: Run the fix script:
```bash
PGPASSWORD=your_password psql -h your_host -U postgres -d vector_db -f 04-fix-vector-db-schema.sql
```

### Issue 2: "schema 'vectors' does not exist"

**Cause**: The DDL scripts weren't run during database initialization.

**Solution**: Same as Issue 1 - run 04-fix-vector-db-schema.sql

### Issue 3: Missing categorization columns

**Cause**: Table was created without categorization support.

**Solution**: Run either:
- `04-fix-vector-db-schema.sql` (complete fix)
- OR `03-add-categorization-to-vector-db.sql` (just add columns)

## Schema Migration History

### Original Schema (Legacy)
- Table location: `public.document_chunks`
- Status: ❌ Deprecated

### Current Schema (Correct)
- Table location: `vectors.document_chunks`
- Status: ✅ Active
- All application code uses this schema

### Why the Change?
- Better organization (separate schema for vector-related tables)
- Cleaner separation from application tables
- Matches best practices for pgvector usage

## Verification

After running the fix script, verify your database:

```sql
-- Connect to vector_db
\c vector_db

-- Check schema exists
SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'vectors';

-- Check table exists
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'vectors' AND table_name = 'document_chunks';

-- Check columns
SELECT column_name, data_type FROM information_schema.columns
WHERE table_schema = 'vectors' AND table_name = 'document_chunks'
ORDER BY ordinal_position;

-- Check indexes
SELECT indexname FROM pg_indexes
WHERE schemaname = 'vectors' AND tablename = 'document_chunks';

-- Check record count
SELECT COUNT(*) FROM vectors.document_chunks;
```

## Production Deployment Checklist

Before deploying to production:

1. ✅ Backup your production database
2. ✅ Review the fix script (04-fix-vector-db-schema.sql)
3. ✅ Test on a staging database first
4. ✅ Run the script on production during low-traffic period
5. ✅ Verify the schema using the queries above
6. ✅ Test document ingestion and search functionality
7. ✅ Monitor application logs for any remaining errors

## Important Notes

- **Never modify these scripts to use `public` schema** - all code expects `vectors` schema
- Scripts use `IF NOT EXISTS` clauses for safety - safe to run multiple times
- The fix script (04) is **idempotent** - running it multiple times won't cause issues
- Always backup before running DDL changes on production
- These scripts only affect the `vector_db` database, not other databases

## Questions?

If you encounter issues:
1. Check application logs for specific error messages
2. Verify database connection string points to correct database
3. Confirm the vectors schema exists: `\dn` in psql
4. Check table exists: `\dt vectors.*` in psql
5. Review this README for common issues
