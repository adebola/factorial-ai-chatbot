# Migration V10: SYSTEM_ADMIN Role and Production URLs

## Overview
This migration (V10) adds the SYSTEM_ADMIN role and updates all OAuth2 registered clients to use production URLs instead of localhost.

## Changes Made

### 1. New Role: SYSTEM_ADMIN
- **Name:** `SYSTEM_ADMIN`
- **ID:** `550e8400-e29b-41d4-a716-446655440003`
- **Description:** System administrator with full system-wide access across all tenants
- **Purpose:** Provides highest level of access for cross-tenant system operations

### 2. Role Hierarchy
After this migration, the system has 4 roles:
1. **USER** - Basic user access (lowest privilege)
2. **TENANT_ADMIN** - Tenant-level administrator
3. **ADMIN** - System admin for a tenant
4. **SYSTEM_ADMIN** - Full cross-tenant system access (highest privilege)

### 3. Updated OAuth2 Client URLs
All `registered_clients` entries are updated to use production URLs:

**Before:**
```json
redirect_uris: ["http://localhost:4200/callback"]
post_logout_redirect_uris: ["http://localhost:4200", "http://localhost:4200/logout"]
```

**After:**
```json
redirect_uris: ["https://app.chatcraft.cc/callback"]
post_logout_redirect_uris: ["https://app.chatcraft.cc", "https://app.chatcraft.cc/logout"]
```

## Migration Details

### File Location
```
authorization-server2/src/main/resources/db/migration/V10__Add_system_admin_role_and_update_client_urls.sql
```

### What the Migration Does

1. **Adds SYSTEM_ADMIN Role:**
   - Inserts new role only if it doesn't already exist
   - Uses fixed UUID for consistency
   - Sets role as active by default

2. **Updates OAuth2 Client URLs:**
   - Replaces `http://localhost:4200` → `https://app.chatcraft.cc`
   - Replaces `http://localhost:3000` → `https://app.chatcraft.cc`
   - Updates both `redirect_uris` and `post_logout_redirect_uris` columns
   - Only updates active clients
   - Updates `updated_at` timestamp

3. **Creates Performance Indexes:**
   - Adds `idx_roles_name_active` composite index
   - Improves query performance for role lookups

4. **Adds Documentation:**
   - Table and column comments explaining role hierarchy
   - Documents expected URL structure

## How to Apply This Migration

### Automatic Application (Recommended)
The migration will run automatically when the Spring Boot application starts if Flyway is configured:

```bash
# Start the authorization server
cd authorization-server2
mvn spring-boot:run
```

Flyway will detect the new V10 migration and apply it automatically.

### Manual Application (If Needed)
If you need to apply the migration manually:

```bash
# Using Flyway CLI
mvn flyway:migrate -Dflyway.configFiles=flyway.conf

# Or using psql directly
psql -h <host> -U <username> -d authorization_db -f src/main/resources/db/migration/V10__Add_system_admin_role_and_update_client_urls.sql
```

## Verification

### 1. Check Roles
```sql
SELECT id, name, description, is_active
FROM roles
WHERE name IN ('USER', 'TENANT_ADMIN', 'ADMIN', 'SYSTEM_ADMIN')
ORDER BY name;
```

**Expected Output:** 4 rows showing all roles including SYSTEM_ADMIN

### 2. Check Updated URLs
```sql
SELECT client_id, redirect_uris, post_logout_redirect_uris
FROM registered_clients
WHERE is_active = true;
```

**Expected Output:** All URLs should use `https://app.chatcraft.cc` instead of `localhost`

### 3. Verify No Localhost URLs Remain
```sql
SELECT client_id, redirect_uris, post_logout_redirect_uris
FROM registered_clients
WHERE (redirect_uris LIKE '%localhost%'
    OR post_logout_redirect_uris LIKE '%localhost%')
    AND is_active = true;
```

**Expected Output:** 0 rows (no localhost URLs in production clients)

### Complete Verification Script
Run the verification queries from:
```
authorization-server2/src/main/resources/db/migration/V10_VERIFICATION_QUERIES.sql
```

## Rollback (If Needed)

If you need to rollback this migration:

```sql
-- Remove SYSTEM_ADMIN role
DELETE FROM user_roles WHERE role_id = '550e8400-e29b-41d4-a716-446655440003';
DELETE FROM roles WHERE id = '550e8400-e29b-41d4-a716-446655440003';

-- Revert URLs to localhost (for development)
UPDATE registered_clients
SET
    redirect_uris = REPLACE(redirect_uris, 'https://app.chatcraft.cc', 'http://localhost:4200'),
    post_logout_redirect_uris = REPLACE(post_logout_redirect_uris, 'https://app.chatcraft.cc', 'http://localhost:4200'),
    updated_at = CURRENT_TIMESTAMP
WHERE is_active = true;

-- Remove the migration entry from Flyway
DELETE FROM flyway_schema_history WHERE version = '10';
```

## Impact on Application

### Frontend Applications
After this migration, frontend applications must use:
- **Production:** `https://app.chatcraft.cc`
- **Callback URL:** `https://app.chatcraft.cc/callback`
- **Logout URL:** `https://app.chatcraft.cc` or `https://app.chatcraft.cc/logout`

### OAuth2 Configuration
Update your OAuth2 client configuration:

```typescript
// Angular/React OAuth2 Config
const authConfig = {
  issuer: 'https://api.chatcraft.cc/auth',
  redirectUri: 'https://app.chatcraft.cc/callback',
  postLogoutRedirectUri: 'https://app.chatcraft.cc',
  clientId: 'webclient',
  scope: 'openid profile read write',
  responseType: 'code',
  // ... other config
};
```

### Backend Services
No changes required for backend services - they continue to use internal service URLs.

## Environment-Specific Considerations

### Development Environment
For local development, you may want to keep localhost URLs. Consider:
1. Using a separate OAuth2 client for development
2. Maintaining a local database with localhost URLs
3. Using environment-specific Flyway profiles

### Production Environment
- ✅ All URLs updated to `https://app.chatcraft.cc`
- ✅ SYSTEM_ADMIN role available for cross-tenant operations
- ✅ Indexes optimized for production load

## Security Considerations

### SYSTEM_ADMIN Role
- **High Privilege:** This role has the highest level of access
- **Assignment:** Only assign to trusted system administrators
- **Audit:** Monitor and log all actions by SYSTEM_ADMIN users
- **Recommendation:** Create a separate audit table for SYSTEM_ADMIN actions

### OAuth2 Client URLs
- **HTTPS Only:** Production URLs use HTTPS for security
- **Domain Verification:** Ensure `app.chatcraft.cc` DNS points to correct application
- **SSL Certificates:** Verify SSL certificates are valid and up-to-date

## Troubleshooting

### Migration Fails with "Role Already Exists"
This is normal if SYSTEM_ADMIN was manually created. The migration uses `WHERE NOT EXISTS` to handle this gracefully.

### URLs Not Updated
Check:
1. Are the clients marked as `is_active = true`?
2. Do the URLs contain 'localhost' before migration?
3. Check `flyway_schema_history` to verify migration ran

### Application Can't Connect After Migration
Verify:
1. Frontend app is using correct production URLs
2. DNS for `app.chatcraft.cc` is configured
3. CORS settings in authorization server allow `app.chatcraft.cc`

## Related Files
- Migration: `V10__Add_system_admin_role_and_update_client_urls.sql`
- Verification: `V10_VERIFICATION_QUERIES.sql`
- Initial Schema: `V1__Create_initial_schema.sql`

## Next Steps
1. Apply migration by starting the application
2. Run verification queries
3. Update frontend OAuth2 configuration
4. Test OAuth2 flow with production URLs
5. Assign SYSTEM_ADMIN role to appropriate users if needed

## Support
For issues or questions about this migration, refer to:
- Flyway documentation: https://flywaydb.org/documentation
- Spring Authorization Server docs: https://spring.io/projects/spring-authorization-server
- Project CLAUDE.md for architecture details
