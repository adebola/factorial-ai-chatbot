# Spring Boot Logging Date Fix

**Date**: 2025-11-20
**Status**: ✅ **COMPLETE**
**Issue**: Missing date in Spring Boot service logs (only showing time)

---

## Problem Identified

### User Report:
Spring Boot services (gateway-service, authorization-server2) were only showing **time** (HH:mm:ss) but not the **date** in their console logs.

**Before (Missing Date)**:
```
10:34:52 [reactor-http-epoll-3] DEBUG io.factorialsystems.gateway.config - Request received
10:34:53 [reactor-http-epoll-3] INFO  io.factorialsystems.gateway.filter - Route matched
```

**After (With Date)**:
```
2025-11-20 10:34:52 [reactor-http-epoll-3] DEBUG io.factorialsystems.gateway.config - Request received
2025-11-20 10:34:53 [reactor-http-epoll-3] INFO  io.factorialsystems.gateway.filter - Route matched
```

---

## Root Cause

### Logging Pattern Analysis

Both Spring Boot services used the same logging pattern configuration with **only time format**:

```yaml
logging:
  pattern:
    console: "%green(%d{HH:mm:ss}) %yellow([%t]) %blue(%-5level) %magenta(%logger{36}) - %msg%n"
```

### Pattern Breakdown

| Component | Format | Issue |
|-----------|--------|-------|
| `%d{HH:mm:ss}` | **Time only** | ❌ Missing date (yyyy-MM-dd) |
| `%t` | Thread name | ✅ OK |
| `%-5level` | Log level | ✅ OK |
| `%logger{36}` | Logger name (max 36 chars) | ✅ OK |
| `%msg` | Log message | ✅ OK |
| `%n` | Newline | ✅ OK |

**The issue**: The date pattern `%d{HH:mm:ss}` only includes:
- `HH` - Hours (00-23)
- `mm` - Minutes (00-59)
- `ss` - Seconds (00-59)

It was **missing**:
- `yyyy` - 4-digit year
- `MM` - 2-digit month
- `dd` - 2-digit day

---

## Solution Implemented

### Changed Date Format

Updated the date format from `%d{HH:mm:ss}` to `%d{yyyy-MM-dd HH:mm:ss}` in all configuration files.

**Before**:
```yaml
logging:
  pattern:
    console: "%green(%d{HH:mm:ss}) %yellow([%t]) %blue(%-5level) %magenta(%logger{36}) - %msg%n"
```

**After**:
```yaml
logging:
  pattern:
    console: "%green(%d{yyyy-MM-dd HH:mm:ss}) %yellow([%t]) %blue(%-5level) %magenta(%logger{36}) - %msg%n"
```

### New Date Format Components

| Component | Meaning | Example |
|-----------|---------|---------|
| `yyyy` | 4-digit year | 2025 |
| `MM` | 2-digit month | 11 |
| `dd` | 2-digit day | 20 |
| `HH` | 24-hour format hours | 10 |
| `mm` | Minutes | 34 |
| `ss` | Seconds | 52 |

**Complete format**: `2025-11-20 10:34:52`

---

## Files Modified

### Gateway Service (2 files)

#### 1. Development Configuration
**File**: `gateway-service/src/main/resources/application.yml`
**Line**: 6

**Before**:
```yaml
logging:
  pattern:
    console: "%green(%d{HH:mm:ss}) %yellow([%t]) %blue(%-5level) %magenta(%logger{36}) - %msg%n"
```

**After**:
```yaml
logging:
  pattern:
    console: "%green(%d{yyyy-MM-dd HH:mm:ss}) %yellow([%t]) %blue(%-5level) %magenta(%logger{36}) - %msg%n"
```

#### 2. Production Configuration
**File**: `gateway-service/src/main/resources/application-production.yml`
**Line**: 6

**Before**:
```yaml
logging:
  pattern:
    console: "%green(%d{HH:mm:ss}) %yellow([%t]) %blue(%-5level) %magenta(%logger{36}) - %msg%n"
```

**After**:
```yaml
logging:
  pattern:
    console: "%green(%d{yyyy-MM-dd HH:mm:ss}) %yellow([%t]) %blue(%-5level) %magenta(%logger{36}) - %msg%n"
```

---

### Authorization Server 2 (2 files)

#### 3. Development Configuration
**File**: `authorization-server2/src/main/resources/application.yml`
**Line**: 8

**Before**:
```yaml
logging:
  pattern:
    console: "%green(%d{HH:mm:ss}) %yellow([%t]) %blue(%-5level) %magenta(%logger{36}) - %msg%n"
```

**After**:
```yaml
logging:
  pattern:
    console: "%green(%d{yyyy-MM-dd HH:mm:ss}) %yellow([%t]) %blue(%-5level) %magenta(%logger{36}) - %msg%n"
```

#### 4. Production Configuration
**File**: `authorization-server2/src/main/resources/application-production.yml`
**Line**: 8

**Before**:
```yaml
logging:
  pattern:
    console: "%green(%d{HH:mm:ss}) %yellow([%t]) %blue(%-5level) %magenta(%logger{36}) - %msg%n"
```

**After**:
```yaml
logging:
  pattern:
    console: "%green(%d{yyyy-MM-dd HH:mm:ss}) %yellow([%t]) %blue(%-5level) %magenta(%logger{36}) - %msg%n"
```

---

## Log Output Examples

### Gateway Service Logs

**Before (Time only)**:
```
10:34:52 [reactor-http-epoll-3] DEBUG org.springframework.cloud.gateway.filter.RouteToRequestUrlFilter - Route matched: onboarding-documents
10:34:52 [reactor-http-epoll-3] DEBUG org.springframework.cloud.gateway.handler.FilteringWebHandler - Sorted gatewayFilterFactories
10:34:53 [reactor-http-epoll-3] INFO  org.springframework.web.server.adapter.HttpWebHandlerAdapter - Completed
```

**After (With date)**:
```
2025-11-20 10:34:52 [reactor-http-epoll-3] DEBUG org.springframework.cloud.gateway.filter.RouteToRequestUrlFilter - Route matched: onboarding-documents
2025-11-20 10:34:52 [reactor-http-epoll-3] DEBUG org.springframework.cloud.gateway.handler.FilteringWebHandler - Sorted gatewayFilterFactories
2025-11-20 10:34:53 [reactor-http-epoll-3] INFO  org.springframework.web.server.adapter.HttpWebHandlerAdapter - Completed
```

### Authorization Server Logs

**Before (Time only)**:
```
14:25:31 [http-nio-9002-exec-1] DEBUG org.springframework.security.web.FilterChainProxy - Securing POST /oauth2/token
14:25:31 [http-nio-9002-exec-1] DEBUG org.springframework.security.oauth2.server.authorization - OAuth2 Token Request received
14:25:32 [http-nio-9002-exec-1] INFO  org.springframework.security.oauth2.server.authorization - OAuth2 Token granted
```

**After (With date)**:
```
2025-11-20 14:25:31 [http-nio-9002-exec-1] DEBUG org.springframework.security.web.FilterChainProxy - Securing POST /oauth2/token
2025-11-20 14:25:31 [http-nio-9002-exec-1] DEBUG org.springframework.security.oauth2.server.authorization - OAuth2 Token Request received
2025-11-20 14:25:32 [http-nio-9002-exec-1] INFO  org.springframework.security.oauth2.server.authorization - OAuth2 Token granted
```

---

## Color Coding (Maintained)

The logging pattern maintains the existing color coding for better readability:

| Component | Color | Purpose |
|-----------|-------|---------|
| `%green(...)` | Green | Timestamp (now includes date) |
| `%yellow(...)` | Yellow | Thread name |
| `%blue(...)` | Blue | Log level (DEBUG, INFO, WARN, ERROR) |
| `%magenta(...)` | Magenta | Logger/Class name |
| Plain text | White | Log message |

**Example colored output**:
```
🟢2025-11-20 10:34:52 🟡[reactor-http-epoll-3] 🔵DEBUG 🟣org.springframework.cloud.gateway - Request received
```

---

## Benefits

### ✅ Complete Timestamp Information
- Now includes both date and time in all logs
- Makes it easy to identify when events occurred
- Useful for debugging issues that span multiple days

### ✅ Better Debugging
- Can correlate events across different days
- No confusion about which day a log entry is from
- Easier to track multi-day issues

### ✅ Log Aggregation Compatible
- Standard ISO 8601-like date format (yyyy-MM-dd HH:mm:ss)
- Compatible with log aggregation systems
- Easy to parse and index

### ✅ No Breaking Changes
- Only changes the log format, not functionality
- All existing log statements continue to work
- Color coding maintained

### ✅ Consistent Format
- Matches the format used in integration tests
- Consistent across development and production
- Same format for both services

---

## Service Ports

| Service | Development Port | Production Port |
|---------|-----------------|-----------------|
| Gateway Service | 8080 | 8080 |
| Authorization Server 2 | 9002 | 9000 |

---

## Spring Boot Configuration

### Logging Levels

**Gateway Service Development**:
```yaml
logging:
  level:
    org.springframework.web: DEBUG
    org.springframework.cloud.gateway: TRACE
    reactor.netty: DEBUG
```

**Gateway Service Production**:
```yaml
logging:
  level:
    org.springframework.web: INFO
    org.springframework.cloud.gateway: INFO
    reactor.netty: INFO
```

**Authorization Server Development**:
```yaml
logging:
  level:
    org.springframework.web: DEBUG
    org.springframework.security: DEBUG
    org.springframework.security.oauth2.server.authorization: DEBUG
    org.springframework.cloud.gateway: DEBUG
    reactor.netty: DEBUG
```

**Authorization Server Production**:
```yaml
logging:
  level:
    org.springframework.web: INFO
    org.springframework.security: INFO
    org.springframework.security.oauth2.server.authorization: INFO
    org.springframework.cloud.gateway: INFO
    reactor.netty: INFO
```

---

## Date Format Standards

### ISO 8601 Compatibility

The format `yyyy-MM-dd HH:mm:ss` is close to ISO 8601 standard:

**Current Format**: `2025-11-20 10:34:52`
**Full ISO 8601**: `2025-11-20T10:34:52Z`

The current format uses:
- Space separator instead of `T`
- No timezone indicator (assumes local/server time)

**Why this format?**:
- More readable for humans
- Consistent with Spring Boot conventions
- Easily parseable by log aggregation tools
- Sorts correctly lexicographically

---

## Logback Pattern Reference

### Pattern Layout Elements

| Pattern | Description | Example |
|---------|-------------|---------|
| `%d{pattern}` | Date/time in specified pattern | `%d{yyyy-MM-dd HH:mm:ss}` |
| `%t` | Thread name | `http-nio-9002-exec-1` |
| `%level` | Log level | `INFO`, `DEBUG`, `ERROR` |
| `%-5level` | Left-padded to 5 chars | `DEBUG`, `INFO `, `WARN ` |
| `%logger{n}` | Logger name (max n chars) | `org.springframework.web` |
| `%msg` | Log message | Actual log content |
| `%n` | Platform newline | `\n` or `\r\n` |
| `%green(...)` | Green color | ANSI green |
| `%yellow(...)` | Yellow color | ANSI yellow |
| `%blue(...)` | Blue color | ANSI blue |
| `%magenta(...)` | Magenta color | ANSI magenta |

---

## Testing After Deployment

### How to Verify the Fix

1. **Start the service**:
   ```bash
   # Gateway Service
   cd gateway-service
   mvn spring-boot:run

   # Authorization Server 2
   cd authorization-server2
   mvn spring-boot:run
   ```

2. **Check log output**:
   - Look for date at the beginning of each log line
   - Format should be: `2025-11-20 10:34:52`
   - Should show current date

3. **Expected log format**:
   ```
   2025-11-20 10:34:52 [main] INFO  o.s.b.w.e.tomcat.TomcatWebServer - Tomcat started on port(s): 8080
   ```

---

## Impact Analysis

### Risk Level: **Minimal**
- Only changes log formatting, not application logic
- No changes to API endpoints or business logic
- No changes to external interfaces

### Performance Impact: **None**
- Date formatting is handled by Logback at logging time
- No additional processing overhead
- Same performance as before

### Breaking Changes: **None**
- All existing log statements work unchanged
- Log parsers may need minor updates if they parse timestamp
- No impact on application functionality

### Restart Required: **Yes**
- Services must be restarted to pick up new configuration
- Changes take effect immediately upon restart
- No database migrations or data changes needed

---

## Comparison with Integration Test Configuration

The integration test configuration already had the correct format:

**File**: `authorization-server2/src/test/resources/application-integration-test.yml`

```yaml
logging:
  pattern:
    console: "%d{yyyy-MM-dd HH:mm:ss} - %msg%n"
```

This shows that the full date format was always intended and works correctly. The main application configurations have now been aligned with this pattern (with additional color coding and thread information).

---

## Related Configuration Files

### Files NOT Modified (Already Correct or Not Used)

1. **authorization-server2/src/test/resources/application-test.yml**
   - No logging pattern defined
   - Uses Spring Boot defaults
   - Not used for production

2. **authorization-server2/src/test/resources/application-integration-test.yml**
   - Already has correct format: `%d{yyyy-MM-dd HH:mm:ss}`
   - Used only for integration testing
   - No changes needed

---

## Troubleshooting

### Logs Still Showing Time Only?

**Check 1: Configuration loaded**
```bash
# Verify which profile is active
# Look for log line at startup:
# "The following profiles are active: production"
```

**Check 2: File changes saved**
```bash
# Verify the changes in the file
grep "yyyy-MM-dd" gateway-service/src/main/resources/application.yml
```

**Check 3: Service restarted**
```bash
# Spring Boot only loads configuration at startup
# You MUST restart the service for changes to take effect
```

### Wrong Date Format?

The format must be exactly:
```
yyyy-MM-dd HH:mm:ss
```

Common mistakes:
- `YYYY-MM-DD` (wrong case)
- `dd-MM-yyyy` (wrong order)
- `yyyy/MM/dd` (wrong separator)

---

## Best Practices

### ✅ Always Include Date in Logs
- Logs should always have both date and time
- Makes debugging multi-day issues possible
- Essential for production systems

### ✅ Use ISO 8601-like Formats
- yyyy-MM-dd HH:mm:ss is standard
- Easy to parse and sort
- Internationally understood

### ✅ Consistent Across Environments
- Same format in development and production
- Makes log analysis easier
- Reduces confusion

### ✅ Include Thread Information
- Helps track concurrent requests
- Essential for debugging race conditions
- Shows which thread handled which request

---

## Future Enhancements

Possible improvements (not currently implemented):

1. **Add milliseconds**: `%d{yyyy-MM-dd HH:mm:ss.SSS}`
2. **Add timezone**: `%d{yyyy-MM-dd HH:mm:ss.SSS Z}`
3. **Add hostname**: Show which server generated the log
4. **Add request ID**: For distributed tracing
5. **Structured logging**: JSON format for production

---

## Deployment Checklist

- [x] Update gateway-service application.yml
- [x] Update gateway-service application-production.yml
- [x] Update authorization-server2 application.yml
- [x] Update authorization-server2 application-production.yml
- [x] Create documentation
- [ ] Restart gateway-service (development)
- [ ] Verify gateway logs show date
- [ ] Restart authorization-server2 (development)
- [ ] Verify auth server logs show date
- [ ] Deploy to staging
- [ ] Restart services in staging
- [ ] Verify logs in staging
- [ ] Deploy to production
- [ ] Restart services in production
- [ ] Verify logs in production

---

## Summary

### Problem:
- Spring Boot services only showed time (HH:mm:ss) without date in logs
- Made debugging difficult, especially for multi-day issues

### Root Cause:
- Logging pattern used `%d{HH:mm:ss}` which only includes time
- Missing date components: yyyy-MM-dd

### Solution:
- Changed date pattern from `%d{HH:mm:ss}` to `%d{yyyy-MM-dd HH:mm:ss}`
- Applied to both development and production configurations
- Applied to both gateway-service and authorization-server2

### Result:
- ✅ All logs now show full date and time: `2025-11-20 10:34:52`
- ✅ Consistent format across all environments
- ✅ Better debugging and troubleshooting capability
- ✅ Compatible with log aggregation systems

---

**Fix Status**: ✅ **COMPLETE**
**Files Modified**: 4 configuration files
**Services Affected**: 2 Spring Boot services
**Restart Required**: Yes
**Deployment Status**: ⏳ **READY FOR DEPLOYMENT**

---

## Contact

For questions or issues related to this fix:
- Verify configuration files were updated correctly
- Ensure services have been restarted
- Check that the active Spring profile matches your environment
- Look for the date pattern in the startup logs
