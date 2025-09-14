# Tenant Migration to OAuth2 Token Claims

## Overview
The onboarding service has been updated to extract tenant information from OAuth2 access token claims instead of directly accessing the tenant database. All tenant database access has been migrated to the authorization server.

## Changes Made

### 1. Updated Dependencies (`app/services/dependencies.py`)
- ✅ **Created `TenantFromToken` class**: Extracts tenant info from JWT claims
- ✅ **Updated `get_current_tenant_from_oauth`**: No longer queries database
- ✅ **Fixed OAuth2 endpoints**: Corrected introspection URL to include `/auth` context path
- ✅ **Role extraction**: Reads user roles from `authorities` claim in token
- ✅ **Backward compatibility**: Added type alias `Tenant = TenantFromToken`

### 2. Token Claims Structure
The JWT access token now includes these claims:
```json
{
  "tenant_id": "uuid-string",
  "user_id": "uuid-string", 
  "email": "user@example.com",
  "full_name": "User Name",
  "api_key": "tenant-api-key",
  "authorities": ["ROLE_USER", "ROLE_ADMIN", "ROLE_TENANT_ADMIN"]
}
```

### 3. Role Mapping
- `ROLE_ADMIN` or `ADMIN` → `TenantRole.ADMIN`
- `ROLE_TENANT_ADMIN` or `TENANT_ADMIN` → `TenantRole.ADMIN`
- Default → `TenantRole.USER`

## API Endpoints That May Need Updates

The following API files still import the database `Tenant` model and may need review:

### Files Using `get_current_tenant` (Priority: High)
- `app/api/payments.py` - Payment processing
- `app/api/website_ingestions.py` - Website scraping
- `app/api/documents.py` - Document management  
- `app/api/subscriptions.py` - Subscription management
- `app/api/widgets.py` - Widget generation
- `app/api/plans.py` - Plan management

### Required Changes Per File
For each API file, update the import:
```python
# Before
from ..models.tenant import Tenant
from ..services.dependencies import get_current_tenant

# After  
from ..services.dependencies import get_current_tenant, Tenant  # Uses TenantFromToken alias
```

## Key Differences: Database Tenant vs TenantFromToken

### Available Fields in `TenantFromToken`
- ✅ `id` (tenant_id from token)
- ✅ `user_id` (current user)
- ✅ `email` (user email) 
- ✅ `full_name` (user name)
- ✅ `api_key` (tenant API key)
- ✅ `role` (user role)
- ✅ `is_active` (always True if token valid)
- ❌ `name` (tenant name - not in token)
- ❌ Database relationships (plan, settings, etc.)

### Migration Strategy for Missing Fields

#### For Tenant Name
```python
# If you need tenant name, call authorization server
# This should be rare - most operations use tenant_id
```

#### For Plan Information  
```python
# Plans are managed separately - use plan_id from tenant if needed
# Call authorization server for full tenant details
```

## Testing Checklist

### 1. Authentication Flow
- [ ] OAuth2 token validation works
- [ ] `tenant_id` extracted from token claims
- [ ] Role-based access control functions
- [ ] Admin endpoints require admin role

### 2. API Endpoints
- [ ] Document upload/management
- [ ] Website ingestion
- [ ] Payment processing  
- [ ] Widget generation
- [ ] Plan management

### 3. Error Handling
- [ ] Missing `tenant_id` in token returns 401
- [ ] Invalid tokens handled properly
- [ ] Role authorization works correctly

## Rollback Plan
If issues arise, temporarily restore database access by:
1. Reverting `dependencies.py` to query database
2. Adding back database session dependency
3. Importing original `Tenant` model

## Next Steps
1. Test all API endpoints with new token-based tenant extraction
2. Update any endpoints that fail due to missing tenant fields
3. Remove unused imports of database `Tenant` model
4. Verify admin role checking works correctly