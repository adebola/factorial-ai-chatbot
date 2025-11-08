# API Key Authentication Implementation

## Problem
Chat service was failing to call billing service usage endpoints in production with error:
```
'utf-8' codec can't decode byte 0x92 in position 0: invalid start byte
Failed to decode JWT header
```

## Root Cause
The chat service was sending the **tenant API key** as a Bearer token to the billing service, but the billing service expected a **JWT token** from the authorization server. The tenant API key is not a valid JWT, causing the decode error.

## Solution
Implemented proper API key authentication following the workflow-service pattern:

### 1. Created TenantClient (`billing-service/app/services/tenant_client.py`)
- **Read-only Redis cache access** (checks cache but never writes)
- Validates tenant API keys via authorization server
- Uses `/tenants/lookup-by-api-key` endpoint
- Includes JWT token detection with helpful error messages
- Caching strategy:
  - First checks `tenant:api:{api_key}` to get tenant_id
  - Then checks `tenant:{tenant_id}` for full tenant data
  - Falls back to authorization server if cache miss

### 2. Added API Key Validation (`billing-service/app/services/dependencies.py`)

#### `validate_api_key()` Function
- Extracts API key from `X-API-Key` header
- Calls `tenant_client.get_tenant_by_api_key()`
- Returns `TokenClaims` with:
  - `tenant_id`: From tenant data
  - `user_id`: "service_account" (no real user context)
  - `authorities`: Empty list (no user roles)

#### `validate_token_or_api_key()` Function
- **Flexible authentication**: Accepts JWT token OR API key
- **Priority**: Tries JWT first, falls back to API key
- **Backward compatible**: Existing JWT token calls continue working
- **New capability**: Supports API key for service-to-service calls

### 3. Updated Usage Endpoints (`billing-service/app/api/usage.py`)

#### `/api/v1/usage/check/{usage_type}`
- Changed from `optional_validate_token` to `validate_token_or_api_key`
- Removed `tenant_id` query parameter (no longer needed)
- Gets tenant_id from `claims.tenant_id` (works for both auth methods)

#### `/api/v1/usage/stats/{tenant_id}`
- Changed from `optional_validate_token` to `validate_token_or_api_key`
- Validates tenant_id matches claims for security
- Supports both JWT and API key authentication

### 4. Updated Chat Service (`chat-service/app/services/usage_cache.py`)
- Sends `X-API-Key` header instead of no authentication
- Pattern: `headers = {"X-API-Key": api_key}`
- Applied to all billing service calls:
  - `/api/v1/usage/stats/{tenant_id}`
  - `/api/v1/usage/check/daily_chats`
  - `/api/v1/usage/check/monthly_chats`

## Authentication Flow

### Internal Service Call (Chat → Billing)
```
1. Chat service has tenant API key from WebSocket connection
2. Chat service sends: X-API-Key: sk_tenant_abc123...
3. Billing service validates API key via TenantClient
4. TenantClient checks Redis cache (read-only)
5. If cache miss, queries authorization server
6. Returns TokenClaims with tenant_id="672c4538-2d8f-..."
7. Endpoint processes request using claims.tenant_id
```

### External User Call (User → Billing)
```
1. User authenticates and receives JWT token
2. User sends: Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
3. Billing service validates JWT token (existing flow)
4. Returns TokenClaims with tenant_id and user_id from token
5. Endpoint processes request using claims.tenant_id
```

## Security Benefits

✅ **Proper Authentication**: API keys validate caller identity, not implicit trust
✅ **Audit Trail**: Track which tenant made each request via API key
✅ **Revocable**: API keys can be revoked if compromised
✅ **Read-Only Cache**: Services only read cache, auth server manages writes (consistency)
✅ **Consistent Pattern**: Same as workflow-service and answer-quality-service
✅ **Backward Compatible**: Existing JWT token calls continue working unchanged

## Files Changed

### Billing Service (3 files)
1. **Created**: `app/services/tenant_client.py` (new file, 145 lines)
2. **Modified**: `app/services/dependencies.py` (added validate_api_key functions, removed optional_validate_token)
3. **Modified**: `app/api/usage.py` (updated both endpoints to use validate_token_or_api_key)

### Chat Service (1 file)
1. **Modified**: `app/services/usage_cache.py` (send X-API-Key header instead of no auth)

## Testing

### Test 1: Internal Service Call (Chat → Billing with API Key)
```bash
# Using API key
curl -H "X-API-Key: <tenant-api-key>" \
  http://localhost:8004/api/v1/usage/stats/672c4538-2d8f-41d4-b160-3e9aff6b3068

# Expected: 200 OK with usage stats
```

### Test 2: External User Call (JWT Token)
```bash
# Get token
TOKEN=$(curl -X POST http://localhost:9000/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password&username=adebola&password=password&client_id=frontend-client&client_secret=secret" \
  | jq -r '.access_token')

# Call with Bearer token
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8004/api/v1/usage/stats/672c4538-2d8f-41d4-b160-3e9aff6b3068

# Expected: 200 OK with usage stats
```

### Test 3: Production Chat Widget
1. Open chat widget on production site
2. Send a message
3. Verify no JWT decode errors in billing service logs
4. Verify usage stats are fetched correctly
5. Verify chat messages work end-to-end

## Deployment

### Build and Deploy Services
```bash
cd /Users/adebola/Documents/Dropbox/ProjectsMacBook/FactorialSystems/Projects/factorialbot/dev/backend

# Build billing service
./docker-build/build-single-service.sh billing-service --no-cache --push

# Build chat service
./docker-build/build-single-service.sh chat-service --no-cache --push
```

### Environment Variables Required
Both services need:
- `REDIS_URL`: Redis connection for cache access
- `AUTHORIZATION_SERVER_URL`: Authorization server URL for tenant lookups

## Comparison with Previous Approach

### Previous (Unauthenticated)
❌ No authentication - relied on network trust
❌ No audit trail of which tenant made requests
❌ No way to revoke access
❌ Security through obscurity

### Current (API Key)
✅ Proper authentication via API keys
✅ Full audit trail via API key tracking
✅ Revocable access control
✅ Read-only cache pattern for consistency
✅ Flexible: Supports both JWT and API key

## Rollback Plan
If issues occur, revert these commits:
1. Billing service: Revert to JWT-only authentication
2. Chat service: Revert to previous no-auth approach
3. Monitor logs for authentication errors
4. Debug and fix before redeploying
