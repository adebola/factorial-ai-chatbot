# Tenant Admin API Reference

Quick reference for the new tenant-scoped chat admin endpoints.

## Authentication

All requests require a valid JWT token with `ROLE_TENANT_ADMIN` authority.

```http
Authorization: Bearer <access_token>
```

## Base URL

```
http://localhost:8000/api/v1/chat
```

## Endpoints

### 1. List Chat Sessions

Get a paginated list of chat sessions for your tenant.

**Endpoint**: `GET /tenant/sessions`

**Query Parameters**:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 50 | Number of sessions to return (1-500) |
| `offset` | integer | 0 | Number of sessions to skip |
| `active_only` | boolean | false | Filter for active sessions only |

**Example Request**:
```bash
curl -X GET "http://localhost:8000/api/v1/chat/tenant/sessions?limit=20&offset=0&active_only=true" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Example Response**:
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "session_id": "sess-abc123",
    "user_identifier": "user@example.com",
    "is_active": true,
    "created_at": "2026-02-05T10:30:00Z",
    "last_activity": "2026-02-05T12:45:00Z",
    "message_count": 15
  }
]
```

**Status Codes**:
- `200 OK` - Success
- `401 Unauthorized` - Missing or invalid token
- `403 Forbidden` - Missing ROLE_TENANT_ADMIN authority
- `422 Unprocessable Entity` - Invalid query parameters

---

### 2. Get Chat Statistics

Get aggregated statistics for your tenant's chat usage.

**Endpoint**: `GET /tenant/stats`

**Query Parameters**: None

**Example Request**:
```bash
curl -X GET "http://localhost:8000/api/v1/chat/tenant/stats" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Example Response**:
```json
{
  "total_sessions": 150,
  "active_sessions": 23,
  "total_messages": 3450,
  "user_messages": 1725,
  "assistant_messages": 1725,
  "recent_messages_24h": 89,
  "tenant_id": "tenant-123"
}
```

**Response Fields**:
| Field | Type | Description |
|-------|------|-------------|
| `total_sessions` | integer | Total number of chat sessions |
| `active_sessions` | integer | Number of currently active sessions |
| `total_messages` | integer | Total number of messages |
| `user_messages` | integer | Number of messages from users |
| `assistant_messages` | integer | Number of messages from AI assistant |
| `recent_messages_24h` | integer | Messages in the last 24 hours |
| `tenant_id` | string | Your tenant ID (from token) |

**Status Codes**:
- `200 OK` - Success
- `401 Unauthorized` - Missing or invalid token
- `403 Forbidden` - Missing ROLE_TENANT_ADMIN authority

---

### 3. Get Session Details

Get detailed information about a specific chat session, including messages.

**Endpoint**: `GET /tenant/sessions/{session_id}`

**Path Parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| `session_id` | string | The session ID to retrieve |

**Query Parameters**:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `message_limit` | integer | 100 | Maximum messages to return (1-1000) |

**Example Request**:
```bash
curl -X GET "http://localhost:8000/api/v1/chat/tenant/sessions/sess-abc123?message_limit=50" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Example Response**:
```json
{
  "session": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "session_id": "sess-abc123",
    "user_identifier": "user@example.com",
    "is_active": true,
    "created_at": "2026-02-05T10:30:00Z",
    "last_activity": "2026-02-05T12:45:00Z",
    "message_count": 15
  },
  "messages": [
    {
      "id": "msg-001",
      "session_id": "sess-abc123",
      "message_type": "user",
      "content": "What is AI?",
      "message_metadata": {},
      "created_at": "2026-02-05T10:30:00Z"
    },
    {
      "id": "msg-002",
      "session_id": "sess-abc123",
      "message_type": "assistant",
      "content": "AI stands for Artificial Intelligence...",
      "message_metadata": {
        "sources": ["doc1.pdf", "doc2.pdf"]
      },
      "created_at": "2026-02-05T10:30:05Z"
    }
  ]
}
```

**Status Codes**:
- `200 OK` - Success
- `401 Unauthorized` - Missing or invalid token
- `403 Forbidden` - Missing ROLE_TENANT_ADMIN authority
- `404 Not Found` - Session doesn't exist or belongs to another tenant
- `422 Unprocessable Entity` - Invalid parameters

---

## Security Notes

### Tenant Isolation
- All endpoints automatically filter data by your `tenant_id` from the JWT token
- You CANNOT access data from other tenants
- You CANNOT override the `tenant_id` filter

### Authorization
- All endpoints require `ROLE_TENANT_ADMIN` in your JWT authorities
- Regular users with `ROLE_USER` will receive 403 Forbidden
- System admins with `ROLE_SYSTEM_ADMIN` should use `/admin/*` routes instead

### Rate Limiting
Standard rate limits apply:
- 100 requests per minute per tenant
- 1000 requests per hour per tenant

---

## Error Responses

### 401 Unauthorized
```json
{
  "detail": "Authorization header missing"
}
```
or
```json
{
  "detail": "Invalid token"
}
```

### 403 Forbidden
```json
{
  "detail": "Admin privileges required"
}
```

### 404 Not Found
```json
{
  "detail": "Session sess-xyz not found or access denied"
}
```

### 422 Unprocessable Entity
```json
{
  "detail": [
    {
      "loc": ["query", "limit"],
      "msg": "ensure this value is less than or equal to 500",
      "type": "value_error.number.not_le"
    }
  ]
}
```

---

## Code Examples

### JavaScript/TypeScript (Axios)

```typescript
import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000/api/v1/chat';

// Configure axios instance with auth
const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Authorization': `Bearer ${accessToken}`
  }
});

// List sessions
async function listSessions(limit = 50, offset = 0, activeOnly = false) {
  const response = await api.get('/tenant/sessions', {
    params: { limit, offset, active_only: activeOnly }
  });
  return response.data;
}

// Get stats
async function getStats() {
  const response = await api.get('/tenant/stats');
  return response.data;
}

// Get session details
async function getSession(sessionId, messageLimit = 100) {
  const response = await api.get(`/tenant/sessions/${sessionId}`, {
    params: { message_limit: messageLimit }
  });
  return response.data;
}
```

### Python (requests)

```python
import requests

API_BASE_URL = 'http://localhost:8000/api/v1/chat'

class TenantChatAPI:
    def __init__(self, access_token):
        self.headers = {'Authorization': f'Bearer {access_token}'}

    def list_sessions(self, limit=50, offset=0, active_only=False):
        response = requests.get(
            f'{API_BASE_URL}/tenant/sessions',
            headers=self.headers,
            params={
                'limit': limit,
                'offset': offset,
                'active_only': active_only
            }
        )
        response.raise_for_status()
        return response.json()

    def get_stats(self):
        response = requests.get(
            f'{API_BASE_URL}/tenant/stats',
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def get_session(self, session_id, message_limit=100):
        response = requests.get(
            f'{API_BASE_URL}/tenant/sessions/{session_id}',
            headers=self.headers,
            params={'message_limit': message_limit}
        )
        response.raise_for_status()
        return response.json()

# Usage
api = TenantChatAPI(access_token)
sessions = api.list_sessions(limit=10)
stats = api.get_stats()
session = api.get_session('sess-abc123')
```

---

## Comparison: Tenant vs System Admin Routes

| Feature | Tenant Admin (`/tenant/*`) | System Admin (`/admin/*`) |
|---------|---------------------------|---------------------------|
| Required Role | `ROLE_TENANT_ADMIN` | `ROLE_SYSTEM_ADMIN` |
| Tenant Scope | Auto-scoped to token | Optional `tenant_id` param |
| Cross-tenant Access | ❌ No | ✅ Yes |
| Data Filtering | Automatic | Manual via parameter |
| Use Case | Tenant self-service | System administration |

---

## Migration Guide

If you're migrating from the old `/admin/*` endpoints:

### Before (System Admin Routes)
```javascript
// Old - requires ROLE_SYSTEM_ADMIN
GET /api/v1/chat/admin/sessions?tenant_id=YOUR_TENANT_ID
GET /api/v1/chat/admin/stats?tenant_id=YOUR_TENANT_ID
```

### After (Tenant Admin Routes)
```javascript
// New - works with ROLE_TENANT_ADMIN, auto-scoped
GET /api/v1/chat/tenant/sessions
GET /api/v1/chat/tenant/stats
```

**Changes needed:**
1. Update endpoint URLs: `/admin/*` → `/tenant/*`
2. Remove `tenant_id` query parameter (now automatic)
3. Ensure your token has `ROLE_TENANT_ADMIN` authority

---

## Support

For issues or questions:
- Check the logs: `chat-service/logs/`
- Review implementation: `TENANT_ADMIN_ROUTES_IMPLEMENTATION.md`
- Test endpoints: Use the Postman/Insomnia collections
- Contact: DevOps team

---

**Last Updated**: February 5, 2026
