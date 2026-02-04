# System Admin 401 Authentication Issue - FIX IMPLEMENTED

## Problem Summary

Super admin users could log in successfully but were immediately logged out with 401 errors on all API calls to the authorization server's admin endpoints (`/api/v1/admin/*`).

## Root Cause

The authorization server's resource server configuration used the default `JwtAuthenticationConverter` which only extracts the `scope` claim from JWT tokens. This resulted in `SCOPE_*` authorities instead of the required `ROLE_*` authorities.

**What was happening:**
1. JWT token generation: ✓ Correctly added `"authorities": ["ROLE_SYSTEM_ADMIN"]` claim
2. Python services: ✓ Correctly extracted `ROLE_SYSTEM_ADMIN` from `authorities` claim
3. Authorization server validation: ✗ Only extracted `scope` claim → `SCOPE_system-admin`
4. API endpoint authorization: ✗ Expected `ROLE_SYSTEM_ADMIN` but got `SCOPE_system-admin` → 401

## Solution Implemented

Added a custom `JwtAuthenticationConverter` bean in `SecurityConfig.java` that extracts authorities from the custom `authorities` claim instead of the default `scope` claim.

## Files Modified

### 1. SecurityConfig.java
**File**: `authorization-server2/src/main/java/io/factorialsystems/authorizationserver2/config/SecurityConfig.java`

#### Changes Made:

1. **Added imports** (lines 29-30):
```java
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
```

2. **Updated apiSecurityFilterChain** (line 82):
```java
// Before:
.oauth2ResourceServer((resourceServer) -> resourceServer
    .jwt(withDefaults()) // Use JWT for API authentication
)

// After:
.oauth2ResourceServer((resourceServer) -> resourceServer
    .jwt(jwt -> jwt.jwtAuthenticationConverter(jwtAuthenticationConverter())) // Use custom converter
)
```

3. **Added new bean method** (lines 201-225):
```java
/**
 * Configure JWT authentication converter to extract authorities from custom "authorities" claim.
 * This is critical for the authorization server to recognize ROLE_* authorities when validating
 * its own tokens for API endpoints (/api/v1/**).
 *
 * Without this, the default converter only extracts the "scope" claim, resulting in SCOPE_*
 * authorities instead of ROLE_* authorities, causing 401 errors on admin endpoints.
 */
@Bean
public JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtGrantedAuthoritiesConverter grantedAuthoritiesConverter = new JwtGrantedAuthoritiesConverter();

    // Extract authorities from custom "authorities" claim instead of default "scope" claim
    grantedAuthoritiesConverter.setAuthoritiesClaimName("authorities");

    // Don't add prefix - our authorities already have "ROLE_" prefix
    grantedAuthoritiesConverter.setAuthorityPrefix("");

    JwtAuthenticationConverter jwtAuthenticationConverter = new JwtAuthenticationConverter();
    jwtAuthenticationConverter.setJwtGrantedAuthoritiesConverter(grantedAuthoritiesConverter);

    log.info("Configured JwtAuthenticationConverter to extract authorities from 'authorities' claim");

    return jwtAuthenticationConverter;
}
```

## Verification

Run the verification script to confirm the fix:

```bash
./verify-jwt-converter-fix.sh
```

Expected output: All checks should pass ✓

## Testing

### Manual Testing Steps:

1. Open admin app: http://localhost:4201
2. Login with system admin credentials:
   - Username: `admin`
   - Password: `password`
3. **Before fix**: Logged out immediately, 401 errors in console
4. **After fix**: Stay logged in, no 401 errors, can access admin features

### What to Verify:

- ✓ User stays logged in after authentication
- ✓ No 401 errors in browser console
- ✓ Admin endpoints return 200 OK responses
- ✓ All admin features are accessible

### Authorization Server Logs:

After the fix, logs should show:
```
Configured JwtAuthenticationConverter to extract authorities from 'authorities' claim
Set SecurityContextHolder to JwtAuthenticationToken [
  Granted Authorities=[ROLE_SYSTEM_ADMIN, ROLE_ADMIN, ROLE_TENANT_ADMIN]
]
```

**Before the fix**, logs showed:
```
Set SecurityContextHolder to JwtAuthenticationToken [
  Granted Authorities=[SCOPE_system-admin, SCOPE_read, ...]
]
```

## Impact

- **Files Changed**: 1 (SecurityConfig.java)
- **Lines Added**: ~25
- **Breaking Changes**: None
- **Services Affected**: Authorization Server only
- **Database Changes**: None
- **Frontend Changes**: None

## Expected Outcome

### Before Fix
- ❌ Admin logs in successfully
- ❌ Immediately logged out
- ❌ All API calls return 401 Unauthorized
- ❌ Browser console shows multiple 401 errors
- ❌ Logs show: `Granted Authorities=[SCOPE_system-admin, ...]`

### After Fix
- ✅ Admin logs in successfully
- ✅ Stays logged in
- ✅ All API calls return 200 OK
- ✅ No 401 errors in browser console
- ✅ Logs show: `Granted Authorities=[ROLE_SYSTEM_ADMIN, ROLE_ADMIN, ROLE_TENANT_ADMIN]`
- ✅ Admin features fully accessible

## Technical Details

### JWT Token Structure (Unchanged)

The JWT token already contains both claims:
```json
{
  "authorities": ["ROLE_SYSTEM_ADMIN", "ROLE_ADMIN", "ROLE_TENANT_ADMIN"],
  "scope": ["system-admin", "read", "openid", "profile", "admin", "write"],
  "tenant_id": "...",
  "user_id": "...",
  "email": "...",
  "full_name": "..."
}
```

### Authority Extraction Flow

**Before Fix:**
```
JWT Token → Default Converter → Extract "scope" claim → SCOPE_* authorities
                                                         ↓
API Endpoint: hasAuthority('ROLE_SYSTEM_ADMIN') → MISMATCH → 401
```

**After Fix:**
```
JWT Token → Custom Converter → Extract "authorities" claim → ROLE_* authorities
                                                              ↓
API Endpoint: hasAuthority('ROLE_SYSTEM_ADMIN') → MATCH → 200 OK
```

## Why This Works

1. JWT tokens already contain the `authorities` claim with correct `ROLE_*` values (added by `tokenCustomizer()`)
2. Python services already extract from `authorities` claim correctly
3. We just needed authorization server to do the same when validating its own API endpoints
4. No changes to JWT structure, endpoints, or other services needed
5. Minimal, focused fix with no side effects

## Date Implemented

2026-01-31

## Author

Fixed by Claude Code based on comprehensive investigation of JWT token generation, validation, and authorization flows.
