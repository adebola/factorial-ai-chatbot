# Diagnose Login 401 Issue

## The Problem

You're experiencing:
1. ✅ Login succeeds (redirect to callback with code)
2. ❌ Automatic logout immediately after
3. ❌ All API calls return 401 Unauthorized
4. ❌ Browser console shows 401 errors

## Diagnostic Steps

### Step 1: Check Browser Console

Open the browser console (F12) and look for:

1. **Token Exchange Success/Failure**:
   - After callback, check Network tab for `/oauth2/token` request
   - Should return 200 with `access_token` in response
   - If it fails, note the error message

2. **API Call Failures**:
   - Look for calls to `/api/v1/admin/*` endpoints
   - Check the HTTP status code (should be 401)
   - Look at the Authorization header being sent
   - Check the error response body

3. **JWT Token Claims**:
   - In Application/Storage tab, check sessionStorage
   - Look for `superadmin_access_token`
   - Copy the token value

### Step 2: Decode the JWT Token

If you got a token, decode it here: https://jwt.io

**Check for these claims:**
- ✅ `authorities`: Should include `["ROLE_SYSTEM_ADMIN", "ROLE_ADMIN", ...]`
- ✅ `scope`: Should include `system-admin`
- ✅ `tenant_id`: Your tenant ID
- ✅ `email`: Your email
- ✅ `exp`: Expiration timestamp (should be in the future)

### Step 3: Check Authorization Server Logs

Look for errors in the authorization server logs:

```bash
# If running in Docker
docker logs authorization-server2

# Or check the console where the server is running
```

**Look for:**
- ❌ "Authentication failed" errors
- ❌ "Access Denied" errors
- ❌ "Invalid token" errors
- ✅ "Configured JwtAuthenticationConverter" message (should appear on startup)

### Step 4: Test API Call Manually

If you have an access token, test it manually:

```bash
# Replace TOKEN with your actual access token from browser
TOKEN="eyJhbGciOiJSUz..."

curl -v -X GET "http://localhost:9002/auth/api/v1/admin/tenants" \
  -H "Authorization: Bearer $TOKEN"
```

**Expected behaviors:**
- ✅ 200 OK = Token is valid and authorization works
- ❌ 401 Unauthorized = Token is invalid or expired
- ❌ 403 Forbidden = Token is valid but lacks required authority

## Common Issues & Fixes

### Issue 1: Token doesn't contain `authorities` claim

**Symptom**: JWT has `scope` but no `authorities` array

**Cause**: Token customizer not working

**Fix**: Check `SecurityConfig.java` has the `tokenCustomizer()` bean

### Issue 2: Token has `authorities` but API still returns 401

**Symptom**: Token has correct claims but authorization fails

**Cause**: JWT converter not extracting authorities correctly

**Fix**: Check `SecurityConfig.java` has the `jwtAuthenticationConverter()` bean and it's used in `apiSecurityFilterChain`

### Issue 3: CORS errors in browser

**Symptom**: Browser console shows CORS errors before 401

**Cause**: CORS misconfiguration

**Fix**: Check `corsConfigurationSource()` in `SecurityConfig.java`

### Issue 4: Token exchange fails at callback

**Symptom**: `/oauth2/token` request returns 400 or 401

**Possible causes**:
- Wrong client_id or client_secret
- Redirect URI mismatch
- Invalid authorization code

## What to Check in Code

### 1. Frontend Environment (environment.ts)

```typescript
oauth2: {
  clientId: 'superadmin-client',  // ✅ Correct
  clientSecret: 'superadmin-secret',  // ✅ Correct
  // ... other settings
}
```

### 2. Backend SecurityConfig (SecurityConfig.java)

**Check these beans exist:**

```java
@Bean
public JwtAuthenticationConverter jwtAuthenticationConverter() {
    // Should extract from "authorities" claim
}

@Bean
OAuth2TokenCustomizer<JwtEncodingContext> tokenCustomizer() {
    // Should add "authorities" claim to token
}
```

**Check API security chain:**

```java
@Bean @Order(2)
SecurityFilterChain apiSecurityFilterChain(HttpSecurity http) {
    // Should use jwtAuthenticationConverter()
}
```

### 3. Database Client Configuration

**Check registered_clients table:**

```sql
SELECT client_id, authorization_grant_types, redirect_uris
FROM registered_clients
WHERE client_id = 'superadmin-client';
```

**Should have:**
- `authorization_grant_types`: Includes "authorization_code" and "refresh_token"
- `redirect_uris`: Includes "http://localhost:4201/callback"

## Next Steps

1. **Collect Information**:
   - Browser console errors (screenshots)
   - Authorization server logs (copy relevant error lines)
   - JWT token (decode at jwt.io and share claims)
   - Network tab showing failed API calls

2. **Share with Developer**:
   - What specific API endpoint is failing first?
   - What's the exact error message in browser console?
   - What does the JWT token contain (authorities claim)?
   - Any errors in authorization server logs?

3. **Temporary Workaround**:
   - Try logging in with Incognito/Private mode (eliminates cached tokens)
   - Clear browser storage completely
   - Try a different browser

## Quick Verification Commands

```bash
# Check if authorization server is running
curl http://localhost:9002/auth/actuator/health

# Check database has superadmin-client
docker exec postgres psql -U postgres -d authorization_db2 -c \
  "SELECT client_id, authorization_grant_types FROM registered_clients WHERE client_id = 'superadmin-client';"

# Check authorization server logs for errors
docker logs authorization-server2 2>&1 | grep -i "error\|fail\|401" | tail -20
```

## File Locations for Reference

- Frontend config: `frontend/chatcraft-superadmin/src/environments/environment.ts`
- Backend security: `authorization-server2/src/main/java/.../config/SecurityConfig.java`
- Auth service: `frontend/chatcraft-superadmin/src/app/core/services/auth.service.ts`
- Database: `authorization_db2` database, `registered_clients` table
