# 🔐 FactorialBot Authentication Guide

## 🚨 **IMPORTANT: API Key vs Access Token Confusion**

There are **TWO DIFFERENT** authentication mechanisms in the system. Using the wrong one will cause authentication failures.

## 🎯 **Authentication Mechanisms**

### 1. **JWT Access Tokens** (For Onboarding Service)
- **Used for**: Authenticated onboarding service endpoints
- **Format**: `eyJ0eXAiOiJKV1Q...` (3 parts separated by dots)
- **Obtained from**: `POST /api/v1/auth/login`
- **Usage**: `Authorization: Bearer <access_token>`

### 2. **Plain API Keys** (For Chat Service & Public Endpoints)
- **Used for**: Chat service, public endpoints, widget authentication
- **Format**: Plain string like `api_key_abc123def456...`
- **Location**: Found in tenant database record
- **Usage**: Query parameter `?api_key=<api_key>`

---

## ✅ **Correct Usage Examples**

### **Chat Service Admin Endpoints**
```bash
# ✅ CORRECT - Use JWT access token (NEW METHOD)
GET /api/v1/chat/admin/sessions?access_token=eyJ0eXAiOiJKV1QiLCJhb...

# ⚠️ DEPRECATED - Plain API keys no longer supported
GET /api/v1/chat/admin/sessions?api_key=your_plain_api_key_here
```

### **Onboarding Service Authenticated Endpoints**
```bash
# ✅ CORRECT - Use JWT token in Authorization header
GET /api/v1/tenants/123
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...

# ❌ WRONG - Don't use plain API key
GET /api/v1/tenants/123?api_key=plain_key
```

### **Public Lookup Endpoints**
```bash
# ✅ CORRECT - Use JWT access token (UPDATED)
GET /api/v1/tenants/lookup?access_token=eyJ0eXAiOiJKV1QiLCJhb...

# ✅ ALSO CORRECT - Public endpoint, no auth needed
GET /api/v1/tenants/123/public
```

---

## 🔄 **Authentication Flow**

### **For Frontend Applications:**

1. **Login to get JWT tokens:**
   ```bash
   POST /api/v1/auth/login
   {
     "username": "tenant_user",
     "password": "password123"
   }
   
   # Response includes:
   {
     "access_token": "eyJ0eXAi...",  # Use for authenticated endpoints
     "tenant_id": "tenant-123"
   }
   ```

2. **Get tenant details (includes API key):**
   ```bash
   GET /api/v1/tenants/tenant-123
   Authorization: Bearer eyJ0eXAi...
   
   # Response includes:
   {
     "id": "tenant-123",
     "api_key": "plain_api_key_abc123",  # Use for chat service
     "name": "Company Name"
   }
   ```

3. **Use appropriate auth for each service:**
   ```bash
   # Onboarding service (authenticated endpoints)
   Authorization: Bearer eyJ0eXAi...
   
   # Chat service (all endpoints)
   ?api_key=plain_api_key_abc123
   ```

---

## 🐛 **Common Issues & Solutions**

### **Issue**: "Tenant not found" when using JWT token with chat service
**Solution**: Extract the `api_key` from your JWT payload and use that instead.

```javascript
// ❌ WRONG
const jwtToken = "eyJ0eXAi...";
fetch(`/api/v1/chat/admin/sessions?api_key=${jwtToken}`)

// ✅ CORRECT
const payload = JSON.parse(atob(jwtToken.split('.')[1]));
const apiKey = payload.api_key;
fetch(`/api/v1/chat/admin/sessions?api_key=${apiKey}`)
```

### **Issue**: "Invalid authentication token" with onboarding service
**Solution**: Use JWT token in Authorization header, not as query parameter.

```bash
# ❌ WRONG
GET /api/v1/tenants/123?token=eyJ0eXAi...

# ✅ CORRECT
GET /api/v1/tenants/123
Authorization: Bearer eyJ0eXAi...
```

---

## 📊 **Endpoint Authentication Quick Reference**

| Service | Endpoint Pattern | Auth Method | Example |
|---------|------------------|-------------|---------|
| **Onboarding** | `/api/v1/tenants/{id}` | JWT Bearer | `Authorization: Bearer eyJ...` |
| **Onboarding** | `/api/v1/documents/**` | JWT Bearer | `Authorization: Bearer eyJ...` |
| **Onboarding** | `/api/v1/tenants/lookup` | JWT Token | `?access_token=eyJ...` |
| **Onboarding** | `/api/v1/tenants/{id}/public` | None | No auth needed |
| **Chat** | `/api/v1/chat/admin/**` | JWT Token | `?access_token=eyJ...` |
| **Chat** | `/ws/chat` | API Key | `?api_key=plain_key` |
| **Gateway** | All routes | Forwards auth | Same as target service |

---

## 🔧 **For Developers**

### **How to identify what you have:**
```javascript
function identifyAuthType(token) {
  if (token.split('.').length === 3) {
    return 'JWT_TOKEN'; // Use with Authorization header
  } else {
    return 'API_KEY';   // Use as query parameter
  }
}
```

### **JWT Token Structure:**
```json
{
  "sub": "tenant-id-123",
  "user_id": "tenant-id-123", 
  "username": "tenant_username",
  "api_key": "plain_api_key_for_chat_service",
  "exp": 1693492800
}
```

The `api_key` field in the JWT payload is what you need for chat service calls!

---

## ⚡ **Quick Fix for Current Issue**

If you're getting "Tenant not found" errors with the chat service admin routes:

1. **Check what you're sending**: Is it a JWT token (3 parts with dots)?
2. **If yes**: Extract the `api_key` from the JWT payload
3. **If no**: Verify the API key exists in your tenant database

The `/api/v1/tenants/lookup` route **IS WORKING CORRECTLY** - it just expects plain API keys, not JWT tokens!