# Cleanup Note: Unused OAuth2 Client

## Background
During the initial implementation, we created an `internal-service-client` OAuth2 client for service-to-service authentication using client credentials flow. This was applied via migration V13.

We later simplified the implementation to use **token forwarding** instead, so this OAuth2 client is no longer needed.

## Current State
- ✅ V13 migration file has been **deleted** (won't apply in future deployments)
- ⚠️ The `internal-service-client` still **exists in the database** (V13 was already applied)
- ✅ The client is **not being used** by any code

## Options

### Option 1: Leave It (Recommended)
- No action needed
- The unused client won't cause any issues
- Simpler and safer

### Option 2: Remove from Database (Optional)
If you want to clean up the database:

```sql
-- Connect to your database
psql -U postgres -d authorization_db2

-- Delete the internal-service-client
DELETE FROM registered_clients WHERE client_id = 'internal-service-client';

-- Mark migration V13 as deleted in flyway_schema_history (optional)
DELETE FROM flyway_schema_history WHERE version = '13';
```

**Note:** Deleting from `flyway_schema_history` means future deployments won't know V13 was ever applied. This is fine since we deleted the migration file.

## Recommendation
**Leave it as-is.** The unused OAuth2 client is harmless and removing it requires manual database intervention across all environments.
