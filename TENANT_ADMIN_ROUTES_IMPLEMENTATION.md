# Tenant Admin Routes Implementation

## Overview

This document describes the implementation of tenant-scoped admin routes for the Chat Service, which resolve the permission issues where tenant admins were getting 403 errors when trying to access chat data through the tenant-admin UI.

## Problem

The chat service had routes like:
- `GET /api/v1/chat/admin/sessions`
- `GET /api/v1/chat/admin/stats`

These routes required `ROLE_SYSTEM_ADMIN` authority, but the tenant-admin UI was trying to access them with `ROLE_TENANT_ADMIN` tokens, resulting in 403 Forbidden errors.

## Solution

Created new tenant-scoped routes (`/tenant/*`) specifically for tenant admins that are automatically scoped to their tenant's data from the JWT token.

### Architecture

```
Role Hierarchy:
├── ROLE_USER - Regular users (WebSocket chat only)
├── ROLE_TENANT_ADMIN - Tenant administrators (can view their own tenant's data)
└── ROLE_SYSTEM_ADMIN - System administrators (can view all tenants' data)

Route Structure:
├── /api/v1/chat/admin/* - System admin routes (ROLE_SYSTEM_ADMIN required)
│   ├── Cross-tenant access
│   └── Optional tenant_id filtering
└── /api/v1/chat/tenant/* - Tenant admin routes (ROLE_TENANT_ADMIN required)
    ├── Auto-scoped to claims.tenant_id
    └── No cross-tenant access
```

## Implemented Routes

### 1. List Tenant Chat Sessions

**Endpoint**: `GET /api/v1/chat/tenant/sessions`

**Authorization**: Requires `ROLE_TENANT_ADMIN`

**Parameters**:
- `limit` (int, 1-500, default: 50) - Number of sessions to return
- `offset` (int, ≥0, default: 0) - Number of sessions to skip for pagination
- `active_only` (bool, default: false) - Filter for active sessions only

**Response**: Array of `ChatSessionResponse` objects

**Security**: Automatically filtered by `claims.tenant_id` from JWT token. Tenant admins can ONLY see their own tenant's sessions.

**Example**:
```bash
GET /api/v1/chat/tenant/sessions?limit=10&offset=0&active_only=false
Authorization: Bearer <tenant_admin_token>
```

### 2. Get Tenant Chat Statistics

**Endpoint**: `GET /api/v1/chat/tenant/stats`

**Authorization**: Requires `ROLE_TENANT_ADMIN`

**Parameters**: None

**Response**: Statistics object containing:
- `total_sessions` - Total number of sessions for the tenant
- `active_sessions` - Number of currently active sessions
- `total_messages` - Total number of messages
- `user_messages` - Number of user messages
- `assistant_messages` - Number of assistant messages
- `recent_messages_24h` - Messages in the last 24 hours
- `tenant_id` - The tenant ID (from token)

**Security**: All stats are automatically scoped to `claims.tenant_id`.

**Example**:
```bash
GET /api/v1/chat/tenant/stats
Authorization: Bearer <tenant_admin_token>
```

### 3. Get Tenant Chat Session Details

**Endpoint**: `GET /api/v1/chat/tenant/sessions/{session_id}`

**Authorization**: Requires `ROLE_TENANT_ADMIN`

**Parameters**:
- `session_id` (path parameter) - The session ID to retrieve
- `message_limit` (int, 1-1000, default: 100) - Max messages to return

**Response**: `ChatSessionWithMessagesResponse` object containing session details and messages

**Security**:
- Verifies session belongs to `claims.tenant_id` before returning
- Returns 404 if session doesn't exist or belongs to another tenant

**Example**:
```bash
GET /api/v1/chat/tenant/sessions/sess-123?message_limit=100
Authorization: Bearer <tenant_admin_token>
```

## Security Features

### Tenant Isolation
- All routes automatically filter by `claims.tenant_id` from the JWT token
- Tenant admins CANNOT specify a different `tenant_id` parameter
- No possibility of cross-tenant data access
- Session detail route verifies ownership before returning data

### Authorization
- All routes use `require_admin()` dependency
- Checks for `ROLE_TENANT_ADMIN` in JWT authorities
- Returns 403 Forbidden if authority is missing

### Logging
All tenant admin access is logged with:
- `tenant_id` - From JWT token
- `user_id` - From JWT token
- Operation details (filters, limits, etc.)

## Files Modified

### Backend Changes

**File**: `chat-service/app/api/admin_chat.py`
- Added import for `require_admin` dependency
- Added import for `status` from FastAPI
- Added 3 new tenant-scoped routes (~200 lines)
  - `GET /tenant/sessions`
  - `GET /tenant/stats`
  - `GET /tenant/sessions/{session_id}`

### Test Files

**File**: `chat-service/tests/test_tenant_admin_routes.py`
- Comprehensive test suite for tenant admin routes
- Tests for tenant isolation security
- Tests for proper error handling
- All 7 tests passing ✅

## Frontend Integration

The tenant-admin UI needs to be updated to use the new endpoints:

### Required Changes

**Old endpoints** (return 403 for tenant admins):
```
GET /api/v1/chat/admin/sessions
GET /api/v1/chat/admin/stats
GET /api/v1/chat/admin/sessions/{session_id}
```

**New endpoints** (work for tenant admins):
```
GET /api/v1/chat/tenant/sessions
GET /api/v1/chat/tenant/stats
GET /api/v1/chat/tenant/sessions/{session_id}
```

### API Response Format

The response formats are identical to the system admin routes, so minimal frontend changes are needed - primarily just updating the URL paths.

## Testing

### Unit Tests

Run the test suite:
```bash
cd chat-service
python -m pytest tests/test_tenant_admin_routes.py -v
```

**Results**: 7 tests passing ✅

### Manual Testing

1. **Get a tenant admin token**:
```bash
# Through your authentication flow
# Token should have authorities: ["ROLE_TENANT_ADMIN"]
```

2. **Test listing sessions**:
```bash
curl -X GET "http://localhost:8000/api/v1/chat/tenant/sessions?limit=10" \
  -H "Authorization: Bearer <tenant_admin_token>"
```

Expected: 200 OK with array of sessions from tenant's data

3. **Test getting stats**:
```bash
curl -X GET "http://localhost:8000/api/v1/chat/tenant/stats" \
  -H "Authorization: Bearer <tenant_admin_token>"
```

Expected: 200 OK with statistics object

4. **Verify isolation** (should fail):
```bash
curl -X GET "http://localhost:8000/api/v1/chat/admin/sessions" \
  -H "Authorization: Bearer <tenant_admin_token>"
```

Expected: 403 Forbidden (tenant admin cannot access system admin routes)

## Verification Checklist

- ✅ Tenant admin routes created and functional
- ✅ All routes properly scoped to `claims.tenant_id`
- ✅ Authorization checks in place (`require_admin`)
- ✅ Proper error handling (404 for non-existent/unauthorized sessions)
- ✅ Comprehensive logging for audit trail
- ✅ Unit tests created and passing (7/7)
- ✅ No syntax errors in Python code
- ✅ Backwards compatible (existing system admin routes unchanged)

## Rollback Plan

If issues arise, simply remove the new tenant routes from `admin_chat.py`:
1. Remove the imports added (`require_admin`, `status`)
2. Remove the entire "TENANT ADMIN ROUTES" section (lines ~279-520)
3. Restart chat service

No database changes were made, so rollback is simple.

## Next Steps

1. **Update Tenant Admin UI**: Change API endpoint URLs from `/admin/*` to `/tenant/*`
2. **Test in Dev Environment**: Verify tenant-admin UI works with new endpoints
3. **Test Tenant Isolation**: Verify tenant A cannot see tenant B's data
4. **Deploy to Production**: Once verified, deploy changes
5. **Monitor Logs**: Watch for any authorization issues in production

## Additional Notes

- System admin routes (`/admin/*`) remain unchanged and still work for system administrators
- This implementation follows the principle of least privilege
- Tenant admins have no way to bypass tenant filtering (security by design)
- The solution is scalable and performant (same database queries, just filtered)
- Response formats are identical between system and tenant routes for consistency

## Support

For questions or issues:
1. Check logs: `chat-service/logs/`
2. Review test cases: `chat-service/tests/test_tenant_admin_routes.py`
3. Contact: DevOps team

---

**Implementation Date**: February 5, 2026
**Status**: Completed ✅
**Tests**: 7/7 Passing ✅
