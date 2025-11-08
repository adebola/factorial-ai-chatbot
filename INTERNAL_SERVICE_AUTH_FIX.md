# ⚠️ SUPERSEDED - Internal Service Authentication Fix

**This approach was replaced with proper API key authentication.**
**See: API_KEY_AUTH_IMPLEMENTATION.md for the final implementation.**

---

# Internal Service Authentication Fix (DEPRECATED)

## Problem
Chat service was failing to call billing service usage endpoints in production with error:
```
'utf-8' codec can't decode byte 0x92 in position 0: invalid start byte
Failed to decode JWT header
```

## Root Cause
The chat service was sending the **tenant API key** as a Bearer token to the billing service, but the billing service expected a **JWT token** from the authorization server. The tenant API key is not a valid JWT, causing the decode error.

## Solution
Modified the billing service to support **optional authentication** for internal service-to-service endpoints:

### 1. New Authentication Dependency (`optional_validate_token`)
Created a new dependency in `app/services/dependencies.py` that:
- Returns `None` if no credentials provided (allows internal service calls)
- Validates JWT token if credentials are provided (supports external API access)
- Used for endpoints that serve both internal services and authenticated users

### 2. Updated Usage Endpoints
Modified two endpoints in `app/api/usage.py`:

#### `/api/v1/usage/check/{usage_type}`
- Changed from `validate_token` to `optional_validate_token`
- Added `tenant_id` query parameter for unauthenticated calls
- Determines tenant from either JWT claims or query parameter

#### `/api/v1/usage/stats/{tenant_id}`
- Changed from `validate_token` to `optional_validate_token`
- Allows unauthenticated internal service calls
- Still enforces tenant access control for authenticated users

### 3. Updated Chat Service
Modified `app/services/usage_cache.py` to:
- Remove Authorization header from billing service calls
- Pass `tenant_id` as query parameter for `/check` endpoints
- Rely on tenant_id in URL path for `/stats` endpoint

## Security Considerations
✅ **Secure**:
- Internal service calls don't require authentication (services run in trusted network)
- Tenant_id is explicitly passed in URL/query params for scope control
- Authenticated users still validated via JWT
- Tenant access control enforced for authenticated requests

## Testing
Test the following scenarios:

### 1. Internal Service Call (Chat → Billing)
```bash
# Should work without auth
curl http://localhost:8004/api/v1/usage/stats/672c4538-2d8f-41d4-b160-3e9aff6b3068
curl "http://localhost:8004/api/v1/usage/check/daily_chats?tenant_id=672c4538-2d8f-41d4-b160-3e9aff6b3068"
```

### 2. Authenticated User Call
```bash
# Get JWT token first
TOKEN=$(curl -X POST http://localhost:9000/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password&username=adebola&password=password&client_id=frontend-client&client_secret=secret" \
  | jq -r '.access_token')

# Should work with valid JWT
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8004/api/v1/usage/stats/672c4538-2d8f-41d4-b160-3e9aff6b3068
```

### 3. Production Chat Flow
- Open chat widget on production site
- Send a message
- Verify no JWT decode errors in billing service logs
- Verify usage stats are fetched correctly

## Files Changed

### Billing Service
1. `app/services/dependencies.py` - Added `optional_validate_token()` function
2. `app/api/usage.py` - Updated both endpoints to use optional auth

### Chat Service
1. `app/services/usage_cache.py` - Removed auth headers, added tenant_id params

## Rollback Plan
If issues occur, revert to JWT-required authentication:
1. Change `optional_validate_token` back to `validate_token` in usage.py
2. Implement service account token system for chat service
3. Have chat service obtain JWT token before calling billing service
