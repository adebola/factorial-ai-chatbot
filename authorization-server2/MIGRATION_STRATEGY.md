# Migration Strategy: Development vs Production

## The Challenge

You have two databases with different states:
- **Development Database:** Roles and registered_clients were manually inserted (not from migrations)
- **Production Database:** Empty, will receive all data from Flyway migrations

The V10 migration needs to work correctly in **both** environments.

## Solution: Idempotent Migration

The V10 migration is designed to be **idempotent** - it can run safely whether the data exists or not.

### How It Works

#### 1. **Roles Table**
The migration uses `INSERT ... WHERE NOT EXISTS`:

```sql
INSERT INTO roles (id, name, description, is_active)
SELECT '550e8400-e29b-41d4-a716-446655440003', 'SYSTEM_ADMIN', 'Description', true
WHERE NOT EXISTS (SELECT 1 FROM roles WHERE name = 'SYSTEM_ADMIN');
```

**Result:**
- ✅ **Dev Database (role exists):** `WHERE NOT EXISTS` returns false → No insert → No error
- ✅ **Prod Database (role missing):** `WHERE NOT EXISTS` returns true → Insert succeeds

#### 2. **Registered Clients URLs**
The migration uses conditional UPDATE:

```sql
UPDATE registered_clients
SET redirect_uris = REPLACE(redirect_uris, 'localhost:4200', 'app.chatcraft.cc')
WHERE redirect_uris LIKE '%localhost%' AND is_active = true;
```

**Result:**
- ✅ **Dev Database (has localhost URLs):** WHERE condition matches → URLs updated
- ✅ **Prod Database (has localhost URLs from V1):** WHERE condition matches → URLs updated
- ✅ **Already updated:** WHERE condition fails → No update → Idempotent

## Testing Strategy

### Test on Development First

Since your dev database has manually-entered data, test there first:

```bash
# 1. Backup dev database
pg_dump -h localhost -U postgres -d authorization_db > backup_dev_$(date +%Y%m%d).sql

# 2. Run the application with V10 migration
cd authorization-server2
mvn spring-boot:run -Dspring.profiles.active=dev

# 3. Check Flyway applied V10
# Look for logs showing "Migration V10 completed"

# 4. Verify the results
psql -h localhost -U postgres -d authorization_db
```

Run these verification queries:

```sql
-- Check roles exist (should show TENANT_ADMIN and SYSTEM_ADMIN)
SELECT name, description FROM roles
WHERE name IN ('TENANT_ADMIN', 'SYSTEM_ADMIN');

-- Check URLs were updated (should see app.chatcraft.cc)
SELECT client_id, redirect_uris, post_logout_redirect_uris
FROM registered_clients;

-- Verify no localhost URLs remain
SELECT COUNT(*) as localhost_count
FROM registered_clients
WHERE redirect_uris LIKE '%localhost%' OR post_logout_redirect_uris LIKE '%localhost%';
-- Should return 0
```

### If Dev Test Succeeds → Deploy to Production

Production deployment will be straightforward:

```bash
# Production database is empty, so all migrations run fresh
docker-compose -f docker-compose-production-optimized.yml up -d authorization-service

# Check logs to verify V10 migration ran
docker logs authorization-service | grep "Migration V10"
```

## What Gets Created/Updated

### In Development Database (Manual Data Exists)

| Table | Action | Result |
|-------|--------|--------|
| **roles** | INSERT WHERE NOT EXISTS | ✅ SYSTEM_ADMIN added (if missing) <br> ✅ TENANT_ADMIN skipped (already exists) |
| **registered_clients** | UPDATE WHERE localhost | ✅ URLs changed to app.chatcraft.cc <br> ✅ `updated_at` timestamp updated |

### In Production Database (Empty)

| Table | Action | Result |
|-------|--------|--------|
| **roles** | INSERT WHERE NOT EXISTS | ✅ All roles created by V1 and V10 |
| **registered_clients** | UPDATE WHERE localhost | ✅ V1 creates with localhost, V10 updates to production |

## Handling Edge Cases

### Case 1: SYSTEM_ADMIN Already Exists in Dev

**Scenario:** You manually created SYSTEM_ADMIN before running migration

**Solution:** ✅ Migration handles this gracefully
```sql
WHERE NOT EXISTS (SELECT 1 FROM roles WHERE name = 'SYSTEM_ADMIN')
```
This checks by **name**, not ID, so it won't try to insert duplicates.

### Case 2: URLs Already Updated Manually

**Scenario:** You already changed localhost to app.chatcraft.cc manually

**Solution:** ✅ Migration is idempotent
```sql
WHERE redirect_uris LIKE '%localhost%'
```
If no localhost URLs exist, the UPDATE affects 0 rows (no error).

### Case 3: Different IDs in Dev vs Prod

**Scenario:** Dev has role ID `abc-123`, Prod will have `550e8400-...`

**Solution:** ✅ No problem - migrations use `WHERE NOT EXISTS` by **name**, not ID
- Dev: Keeps existing role with different ID
- Prod: Creates role with standard ID from migration

### Case 4: Multiple Clients with Localhost URLs

**Scenario:** You have multiple registered_clients in dev

**Solution:** ✅ UPDATE affects all matching rows
```sql
UPDATE registered_clients ... WHERE redirect_uris LIKE '%localhost%'
```
All clients with localhost URLs get updated.

## Rollback Plan (If Needed)

If something goes wrong, you can rollback:

### Development Database
```sql
-- Restore from backup
psql -h localhost -U postgres -d authorization_db < backup_dev_20250129.sql

-- Or rollback just the migration
DELETE FROM flyway_schema_history WHERE version = '10';
```

### Production Database
```sql
-- Revert URLs to localhost (for testing)
UPDATE registered_clients
SET
    redirect_uris = REPLACE(redirect_uris, 'https://app.chatcraft.cc', 'http://localhost:4200'),
    post_logout_redirect_uris = REPLACE(post_logout_redirect_uris, 'https://app.chatcraft.cc', 'http://localhost:4200')
WHERE is_active = true;

-- Remove SYSTEM_ADMIN role (if needed)
DELETE FROM user_roles WHERE role_id IN (SELECT id FROM roles WHERE name = 'SYSTEM_ADMIN');
DELETE FROM roles WHERE name = 'SYSTEM_ADMIN';

-- Remove Flyway entry
DELETE FROM flyway_schema_history WHERE version = '10';
```

## Pre-Migration Checklist

Before running V10 migration:

- [ ] Backup development database
- [ ] Review current roles in dev: `SELECT * FROM roles;`
- [ ] Review current clients in dev: `SELECT * FROM registered_clients;`
- [ ] Verify Flyway is configured correctly
- [ ] Check app can connect to database
- [ ] Ensure `flyway_schema_history` table exists

## Post-Migration Checklist

After V10 migration runs:

- [ ] Verify SYSTEM_ADMIN role exists
- [ ] Verify TENANT_ADMIN role exists
- [ ] Verify all client URLs use app.chatcraft.cc
- [ ] Verify no localhost URLs remain in production
- [ ] Check `flyway_schema_history` shows version 10
- [ ] Test OAuth2 login flow with new URLs
- [ ] Update frontend config to use new URLs

## Expected Flyway Output

### Development (With Existing Data)
```
INFO: Migrating schema "public" to version "10" - Add system admin role and update client urls
INFO: Successfully applied 1 migration to schema "public" (execution time 00:00.234s)
NOTICE: Migration V10 completed: 1 active registered_clients now use production URLs
```

### Production (Empty Database)
```
INFO: Migrating schema "public" to version "1" - Create initial schema
INFO: Migrating schema "public" to version "2" - Remove tenant from registered clients
...
INFO: Migrating schema "public" to version "10" - Add system admin role and update client urls
INFO: Successfully applied 10 migrations to schema "public" (execution time 00:01.456s)
NOTICE: Migration V10 completed: 1 active registered_clients now use production URLs
```

## Troubleshooting

### "Duplicate key value violates unique constraint"

**Cause:** Role or client with same name already exists

**Solution:** The migration is designed to prevent this with `WHERE NOT EXISTS`. If you see this error, it means the condition isn't working as expected.

**Fix:**
```sql
-- Check what exists
SELECT * FROM roles WHERE name IN ('TENANT_ADMIN', 'SYSTEM_ADMIN');

-- If duplicate, the migration's WHERE NOT EXISTS should have caught it
-- Contact support with error details
```

### "Column 'redirect_uris' not found"

**Cause:** Database schema doesn't match expected structure

**Solution:** Ensure all previous migrations (V1-V9) ran successfully
```sql
SELECT version, description, success
FROM flyway_schema_history
ORDER BY installed_rank;
```

### Migration Runs But URLs Not Updated

**Cause:** URLs don't contain 'localhost' string

**Check:**
```sql
SELECT client_id, redirect_uris, post_logout_redirect_uris
FROM registered_clients;
```

**Fix:** If URLs are different (e.g., `127.0.0.1`), update the migration:
```sql
UPDATE registered_clients
SET redirect_uris = REPLACE(redirect_uris, '127.0.0.1', 'app.chatcraft.cc')
WHERE redirect_uris LIKE '%127.0.0.1%';
```

## Best Practices Going Forward

1. **Always use Flyway migrations** for schema and reference data changes
2. **Never manually insert** roles or OAuth2 clients in production
3. **Test migrations on dev first** before deploying to prod
4. **Keep dev and prod schemas in sync** by running all migrations
5. **Backup before migrating** production database
6. **Use environment-specific data** where necessary (dev vs prod URLs)

## References

- Flyway Documentation: https://flywaydb.org/documentation
- Idempotent Migrations: https://flywaydb.org/documentation/concepts/migrations#repeatable-migrations
- PostgreSQL Conditional INSERT: https://www.postgresql.org/docs/current/sql-insert.html
- Project Migration Files: `authorization-server2/src/main/resources/db/migration/`
