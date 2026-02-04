# Tenant Statistics Enhancement - Implementation Summary

## Overview
Enhanced the `GET /api/v1/admin/tenants/{tenant_id}/statistics` endpoint in authorization-server2 to retrieve comprehensive statistics from chat and onboarding services using **simple token forwarding**.

## Implementation Approach: Token Forwarding

Instead of creating a complex OAuth2 client credentials flow, we use a **simple and elegant approach**:

1. **System admin authenticates** and gets an access token with `ROLE_SYSTEM_ADMIN`
2. **Authorization server receives the request** with the token in the `Authorization` header
3. **Authorization server forwards the same token** to chat and onboarding services
4. **Chat and onboarding services validate the token** and return statistics
5. **Authorization server aggregates** all statistics and returns to the client

### Why This Works
- The admin's token already has `ROLE_SYSTEM_ADMIN` authority
- Chat and onboarding admin endpoints require `ROLE_SYSTEM_ADMIN`
- No need for separate service-to-service authentication
- Simpler, fewer moving parts, easier to debug

## What Was Implemented

### Phase 1: Onboarding Service Admin Endpoint ✅

**New File**: `onboarding-service/app/api/admin_stats.py`
- Endpoint: `GET /api/v1/admin/stats?tenant_id={id}`
- Authentication: Requires `ROLE_SYSTEM_ADMIN` via `require_system_admin` dependency
- Returns:
  - `num_documents`: Total count of documents
  - `num_websites`: Total count of website ingestions
  - `storage_used_mb`: Total file storage in MB (sum of Document.file_size)
  - Status breakdowns for documents and websites

**Modified**: `onboarding-service/app/main.py`
- Imported and registered `admin_stats_router` with prefix `/api/v1/admin`

### Phase 2: Service HTTP Clients ✅

**New File**: `authorization-server2/src/main/java/.../service/ChatServiceClient.java`
- HTTP client for communicating with Chat Service
- Method: `getChatStats(String tenantId, String authorizationHeader)`
  - Accepts the `Authorization` header from the incoming request
  - Forwards it to the chat service
  - Returns chat statistics as a Map
- Health check: `isChatServiceAvailable()`
- 10-second timeout for all requests

**Modified**: `authorization-server2/src/main/java/.../service/OnboardingServiceClient.java`
- New method: `getOnboardingStats(String tenantId, String authorizationHeader)`
  - Accepts the `Authorization` header from the incoming request
  - Forwards it to the onboarding service
  - Returns onboarding statistics as a Map

### Phase 3: Enhanced Tenant Statistics ✅

**Modified**: `authorization-server2/src/main/java/.../controller/TenantAdminController.java`
- Injected `ChatServiceClient` and `OnboardingServiceClient`
- Enhanced `getTenantStatistics()` method:
  - **Accepts `@RequestHeader("Authorization") String authorizationHeader`**
  - Retrieves chat stats by forwarding the token: `chatServiceClient.getChatStats(id, authorizationHeader)`
  - Retrieves onboarding stats by forwarding the token: `onboardingServiceClient.getOnboardingStats(id, authorizationHeader)`
  - Implements graceful degradation (returns zeros if services unavailable)
  - Logs all service failures for monitoring
- Added helper methods:
  - `getLongValue(Map, String)`: Safely extract long values
  - `getDoubleValue(Map, String)`: Safely extract double values

**Modified**: `authorization-server2/src/main/resources/application.yml`
- Added chat service URL: `chat.service.url: http://localhost:8000`

## Final Response Structure

The `/api/v1/admin/tenants/{tenant_id}/statistics` endpoint now returns:

```json
{
  "total_users": 15,
  "active_users": 12,
  "total_chats": 234,
  "total_messages": 1567,
  "num_documents": 25,
  "num_websites": 3,
  "storage_used_mb": 156.75,
  "last_activity": "2026-01-30T10:30:00Z"
}
```

## Error Handling & Graceful Degradation

- If chat service is unavailable: `total_chats=0`, `total_messages=0`
- If onboarding service is unavailable: `num_documents=0`, `num_websites=0`, `storage_used_mb=0`
- User statistics always available (local to authorization server)
- All service failures logged with detailed error messages

## Testing

**Test Script**: `test-tenant-statistics.sh`
- Obtains system admin token (password grant or environment variable)
- Tests onboarding stats endpoint with the token
- Tests chat stats endpoint with the token
- Tests enhanced tenant statistics endpoint (which forwards the token)
- Verifies all fields are present in response

**To Run Tests**:
```bash
# 1. Ensure all services are running:
#    - Authorization Server (port 9002)
#    - Chat Service (port 8000)
#    - Onboarding Service (port 8001)

# 2. Rebuild and restart authorization server to load new code
mvn clean install -DskipTests
# Then restart the application

# 3. Run test script
./test-tenant-statistics.sh
```

## Manual Testing

### 1. Get System Admin Token
```bash
# Option 1: Using password grant (adjust client_id/secret as needed)
curl -X POST http://localhost:9002/auth/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password&username=adebola&password=password&client_id=webclient&client_secret=secret123"

# Option 2: Get token from your admin application
# Then export it: export ACCESS_TOKEN='your-token-here'
```

### 2. Test Onboarding Stats (with forwarded token)
```bash
TENANT_ID="5190e7b2-04c1-477d-8dca-84462baf7bd3"

curl -H "Authorization: Bearer $ACCESS_TOKEN" \
  "http://localhost:8001/api/v1/admin/stats?tenant_id=$TENANT_ID"
```

### 3. Test Chat Stats (with forwarded token)
```bash
curl -H "Authorization: Bearer $ACCESS_TOKEN" \
  "http://localhost:8000/api/v1/admin/stats?tenant_id=$TENANT_ID"
```

### 4. Test Enhanced Tenant Statistics (forwards token internally)
```bash
curl -H "Authorization: Bearer $ACCESS_TOKEN" \
  "http://localhost:9002/auth/api/v1/admin/tenants/$TENANT_ID/statistics"
```

## Architecture Benefits

1. **Simplicity**: No separate OAuth2 client credentials flow needed
2. **Token Reuse**: Forwards the same admin token to all services
3. **Standard Pattern**: Common microservices pattern (API Gateway style)
4. **Graceful Degradation**: Partial data returned even if some services are down
5. **Separation of Concerns**: Each service owns its own statistics
6. **Extensible**: Easy to add more statistics from other services in the future
7. **Secure**: All inter-service communication uses Bearer tokens with system-admin scope
8. **No Additional Complexity**: No token caching, refresh logic, or additional OAuth2 clients

## Comparison: Complex vs Simple Approach

### ❌ Complex Approach (Initial Implementation)
- ServiceTokenProvider with token caching
- OAuth2 client credentials grant
- Internal service OAuth2 client (V13 migration)
- Token refresh logic
- Additional configuration in application.yml
- ~150 lines of code for token management

### ✅ Simple Approach (Current Implementation)
- Extract token from incoming request: `@RequestHeader("Authorization")`
- Forward token to other services: `service.getStats(id, authHeader)`
- ~5 lines of code
- No additional OAuth2 clients needed
- No token caching or refresh needed

## Files Modified

### New Files (3)
1. `onboarding-service/app/api/admin_stats.py`
2. `authorization-server2/src/main/java/.../service/ChatServiceClient.java`
3. `IMPLEMENTATION_SUMMARY.md` (this file)

### Modified Files (4)
1. `onboarding-service/app/main.py`
2. `authorization-server2/src/main/java/.../service/OnboardingServiceClient.java`
3. `authorization-server2/src/main/java/.../controller/TenantAdminController.java`
4. `authorization-server2/src/main/resources/application.yml`

### Deleted Files (2)
1. ~~`ServiceTokenProvider.java`~~ (not needed with token forwarding)
2. ~~`V13__Add_internal_service_oauth2_client.sql`~~ (not needed with token forwarding)

## Next Steps

1. **Rebuild Authorization Server**:
   ```bash
   cd authorization-server2
   mvn clean install -DskipTests
   ```

2. **Restart Authorization Server**: Stop and restart to load the new code

3. **Run Tests**: Execute `./test-tenant-statistics.sh` to verify implementation

4. **Test Graceful Degradation**: Stop chat or onboarding service and verify zeros are returned

5. **Monitor Logs**: Check authorization server logs for service calls

## Notes

- No new Python dependencies required
- No new Java dependencies required
- No database migrations needed (deleted V13)
- Authorization server build should complete successfully
- All code follows existing patterns (BillingServiceClient for reference, but simpler)
- **Much simpler than the initial complex implementation!**

## When Would You Need the Complex Approach?

The OAuth2 client credentials flow (ServiceTokenProvider) would only be needed for:

- **Background jobs** (cron tasks, scheduled cleanup) that run without user context
- **System-initiated events** (e.g., nightly reports, automated maintenance)
- **Service-to-service calls outside HTTP requests** (message queue consumers, etc.)

For **request handlers** where a user token is already present, token forwarding is the right choice.
