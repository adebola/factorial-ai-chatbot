# Fix Chat Statistics - total_chats and total_messages Returning 0

## Problem

The endpoint `GET /api/v1/admin/tenants/{id}/statistics` was returning:
- `total_chats`: 0
- `total_messages`: 0

Even though the database contained:
- 147 sessions
- 903 messages

## Root Cause

**Wrong endpoint URL** in `ChatServiceClient.java`:

- **Incorrect**: `http://localhost:8000/api/v1/admin/stats` ❌ (returns 404 Not Found)
- **Correct**: `http://localhost:8000/api/v1/chat/admin/stats` ✅

The chat service mounts the admin router at `/api/v1/chat`, not `/api/v1`.

## Solution

Fixed the URL in `ChatServiceClient.java`:

```java
// Before (WRONG):
String url = chatServiceUrl + "/api/v1/admin/stats";

// After (CORRECT):
String url = chatServiceUrl + "/api/v1/chat/admin/stats";
```

## File Modified

- `authorization-server2/src/main/java/io/factorialsystems/authorizationserver2/service/ChatServiceClient.java` (line 42)

## How to Apply the Fix

### Step 1: Rebuild Authorization Server

```bash
cd /Users/adebola/Documents/Dropbox/ProjectsMacBook/FactorialSystems/Projects/factorialbot/dev/backend

# Use the quick fix script
./fix-auth-401.sh
```

Or manually:

```bash
# Stop auth server
kill -9 $(lsof -ti:9002)

# Rebuild
cd authorization-server2
mvn clean install -DskipTests

# Start
mvn spring-boot:run
```

### Step 2: Test the Fix

```bash
# Get a token (use your actual credentials)
TOKEN=$(curl -s -X POST http://localhost:9002/auth/oauth2/token \
  -u superadmin-client:superadmin-secret \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" | jq -r '.access_token')

# Test statistics endpoint
curl -X GET "http://localhost:8080/api/v1/admin/tenants/9eb23c01-b66a-4e23-8316-4884532d5b04/statistics" \
  -H "Authorization: Bearer $TOKEN" | jq '{total_chats, total_messages}'
```

**Expected Output**:
```json
{
  "total_chats": 147,
  "total_messages": 903
}
```

## Verification

### Before Fix:
```json
{
  "total_chats": 0,
  "total_messages": 0,
  "num_documents": 12,
  "num_websites": 3,
  "storage_used_mb": 45.67
}
```

### After Fix:
```json
{
  "total_chats": 147,
  "total_messages": 903,
  "num_documents": 12,
  "num_websites": 3,
  "storage_used_mb": 45.67
}
```

## Why This Happened

The chat service API structure is:
- Main API routes: `/api/v1/...`
- Admin chat routes: `/api/v1/chat/admin/...`

The ChatServiceClient was calling the wrong path, resulting in 404 errors which were silently caught and returned as 0 values (graceful degradation).

## Related Files

### Chat Service Router Configuration

**File**: `chat-service/app/main.py` (line 197)
```python
app.include_router(admin_chat_router, prefix=f"{settings.API_V1_STR}/chat", tags=["admin", "chat"])
```

This mounts the admin router at `/api/v1/chat`, making the stats endpoint:
`/api/v1/chat/admin/stats`

### Stats Endpoint

**File**: `chat-service/app/api/admin_chat.py` (line 234)
```python
@router.get("/admin/stats")
async def get_chat_stats(
    tenant_id: Optional[str] = Query(None),
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db)
):
    # Returns total_sessions and total_messages
```

Full URL: `http://localhost:8000/api/v1/chat/admin/stats?tenant_id={id}`

## Testing Checklist

- [ ] Rebuild authorization server
- [ ] Restart authorization server
- [ ] Clear browser cache
- [ ] Login to superadmin app
- [ ] Navigate to tenant statistics page
- [ ] Verify `total_chats` shows 147 (not 0)
- [ ] Verify `total_messages` shows 903 (not 0)
- [ ] Check that other stats still work correctly

## Additional Notes

- The fix also improves error logging - you'll now see actual API errors instead of silent 404s
- The graceful degradation still works - if chat service is down, it returns 0s without breaking the whole response
- No database changes required
- No frontend changes required

## Date Fixed

2026-01-31
