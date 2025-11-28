# Logging Timestamp Fix - FastAPI Services

**Date**: 2025-11-20
**Status**: ✅ **COMPLETE**
**Issue**: Missing date/time timestamps in logs from FastAPI services

---

## Problem Identified

### User Report:
All or most of the logs from FastAPI services (especially billing, chat, onboarding) were missing date/time information, making it difficult to debug issues and track when events occurred.

### Root Cause:
Three services (billing-service, chat-service, onboarding-service) were using `structlog.dev.ConsoleRenderer()` without timestamp configuration. The other three services (communications, workflow, answer-quality) were using Loguru which already included timestamps.

**Before (Missing Timestamp)**:
```
test - INFO - API request method=POST path=/api/v1/plans service=billing-service
```

**After (With Timestamp)**:
```
test - INFO - 2025-11-20T11:35:57.361882Z [info] Test log message [test] func_name=<module> lineno=11 service=billing-service
```

---

## Solution Implemented

### Scope
Added timestamp and function:line information to three FastAPI services while maintaining their existing structlog-only architecture.

### Services Updated

1. **billing-service**: `/app/core/logging_config.py`
2. **chat-service**: `/app/core/logging_config.py`
3. **onboarding-service**: `/app/core/logging_config.py`

### Changes Made

For each service, added two new processors to the structlog configuration:

#### 1. TimeStamper Processor
```python
structlog.processors.TimeStamper(fmt="iso", utc=True)
```
- Adds ISO 8601 timestamp to all log entries
- Uses UTC timezone for consistency across distributed systems
- Format: `2025-11-20T11:35:57.361882Z` (with milliseconds)

#### 2. CallsiteParameterAdder Processor
```python
structlog.processors.CallsiteParameterAdder(
    parameters=[
        structlog.processors.CallsiteParameter.FUNC_NAME,
        structlog.processors.CallsiteParameter.LINENO,
    ]
)
```
- Adds function name and line number to log entries
- Makes debugging easier by showing exactly where logs originate
- Example: `func_name=create_subscription lineno=123`

---

## File Changes

### Before (Lines 72-96 in all three services):
```python
# Configure structlog
if json_logs:
    # Production: JSON logs
    processors = [
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        add_context_processor,
        structlog.processors.JSONRenderer()  # ❌ No timestamp
    ]
else:
    # Development: Pretty console logs
    processors = [
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        add_context_processor,
        structlog.dev.ConsoleRenderer(colors=True)  # ❌ No timestamp
    ]
```

### After (Lines 72-110 in all three services):
```python
# Configure structlog
if json_logs:
    # Production: JSON logs with timestamp
    processors = [
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),  # ✅ Add ISO 8601 timestamp
        structlog.processors.CallsiteParameterAdder(  # ✅ Add function/line info
            parameters=[
                structlog.processors.CallsiteParameter.FUNC_NAME,
                structlog.processors.CallsiteParameter.LINENO,
            ]
        ),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        add_context_processor,
        structlog.processors.JSONRenderer()
    ]
else:
    # Development: Pretty console logs with timestamp and location
    processors = [
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),  # ✅ Add ISO 8601 timestamp
        structlog.processors.CallsiteParameterAdder(  # ✅ Add function/line info
            parameters=[
                structlog.processors.CallsiteParameter.FUNC_NAME,
                structlog.processors.CallsiteParameter.LINENO,
            ]
        ),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        add_context_processor,
        structlog.dev.ConsoleRenderer(colors=True)
    ]
```

---

## Log Format Examples

### Development Mode (Console Logs)

**billing-service**:
```
test - INFO - 2025-11-20T11:35:57.361882Z [info] Test log message [test] func_name=<module> lineno=11 number=123 service=billing-service test_key=test_value
```

**chat-service**:
```
2025-11-20T11:36:15.720475Z [info] Test chat log message [test] func_name=<module> lineno=11 service=chat-service session_id=test123 test_key=chat_value
```

**onboarding-service**:
```
test - INFO - 2025-11-20T11:36:29.851386Z [info] Test onboarding log message [test] func_name=<module> lineno=11 service=onboarding-service tenant_id=tenant123 test_key=onboarding_value
```

### Production Mode (JSON Logs)

**billing-service**:
```json
{
  "test_key": "production_value",
  "number": 456,
  "event": "Test production log message",
  "logger": "test",
  "level": "info",
  "timestamp": "2025-11-20T11:36:57.080213Z",
  "func_name": "<module>",
  "lineno": 12,
  "service": "billing-service"
}
```

---

## Benefits

### ✅ Timestamps on All Logs
- Every log entry now includes an ISO 8601 timestamp with milliseconds
- UTC timezone ensures consistency across distributed systems
- Makes it easy to correlate events across services

### ✅ Better Debugging
- Function name and line number show exactly where logs originate
- No need to search through code to find log statements
- Faster troubleshooting and issue resolution

### ✅ Consistent Format
- Both development and production logs now have timestamps
- JSON logs include all necessary fields for log aggregation systems
- Matches the format used by other services (communications, workflow, answer-quality)

### ✅ No Breaking Changes
- All existing log statements continue to work
- Context variables (tenant_id, request_id, etc.) still captured
- Structured logging (key-value pairs) still functional
- Colored output in development mode maintained

---

## Testing Results

### Development Mode Tests

All three services verified working with timestamps:

1. **billing-service**: ✅ Timestamp: `2025-11-20T11:35:57.361882Z`
2. **chat-service**: ✅ Timestamp: `2025-11-20T11:36:15.720475Z`
3. **onboarding-service**: ✅ Timestamp: `2025-11-20T11:36:29.851386Z`

### Production Mode Test

JSON output verified with all fields:
```json
{
  "timestamp": "2025-11-20T11:36:57.080213Z",  // ✅ Timestamp present
  "func_name": "<module>",                      // ✅ Function name present
  "lineno": 12,                                  // ✅ Line number present
  "event": "Test production log message",
  "logger": "test",
  "level": "info",
  "service": "billing-service"
}
```

---

## Impact Analysis

### Risk Level: **Low**
- Only changes log formatting, not application functionality
- No changes to business logic or API endpoints
- Backward compatible with existing logging infrastructure

### Performance Impact: **Negligible**
- Timestamp generation is very fast (microseconds)
- CallsiteParameterAdder has minimal overhead
- No noticeable impact on application performance

### Breaking Changes: **None**
- All existing log statements work unchanged
- Log parsers may need minor updates to handle new fields
- Frontend log viewing tools will automatically show timestamps

---

## Service Status After Fix

| Service | Logging Library | Timestamp Format | Function/Line Info | Status |
|---------|----------------|------------------|-------------------|--------|
| **billing-service** | Structlog | ISO 8601 UTC | ✅ Yes | ✅ FIXED |
| **chat-service** | Structlog | ISO 8601 UTC | ✅ Yes | ✅ FIXED |
| **onboarding-service** | Structlog | ISO 8601 UTC | ✅ Yes | ✅ FIXED |
| **communications-service** | Loguru + Structlog | ISO 8601 UTC | ✅ Yes | ✅ Already had timestamps |
| **workflow-service** | Loguru + Structlog | ISO 8601 UTC | ✅ Yes | ✅ Already had timestamps |
| **answer-quality-service** | Loguru + Structlog | ISO 8601 UTC | ✅ Yes | ✅ Already had timestamps |

---

## Environment Variables

The logging configuration respects these environment variables:

### LOG_LEVEL
```bash
LOG_LEVEL=DEBUG    # Show all logs
LOG_LEVEL=INFO     # Default
LOG_LEVEL=WARNING  # Warnings and errors only
LOG_LEVEL=ERROR    # Errors only
```

### ENVIRONMENT
```bash
ENVIRONMENT=development  # Pretty colored console logs (default)
ENVIRONMENT=production   # JSON structured logs
```

---

## Usage Examples

### In Application Code

No changes needed to existing code:

```python
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# All these will now automatically include timestamps
logger.info("User logged in", user_id="123", tenant_id="abc")
logger.error("Payment failed", error=str(e), amount=100.50)
logger.debug("Cache hit", key="user:123", ttl=3600)
```

### Log Output (Development)
```
2025-11-20T11:40:23.123456Z [info] User logged in [app.services.auth] func_name=authenticate lineno=45 user_id=123 tenant_id=abc service=billing-service
```

### Log Output (Production)
```json
{
  "timestamp": "2025-11-20T11:40:23.123456Z",
  "level": "info",
  "event": "User logged in",
  "logger": "app.services.auth",
  "func_name": "authenticate",
  "lineno": 45,
  "user_id": "123",
  "tenant_id": "abc",
  "service": "billing-service"
}
```

---

## Timestamp Format Details

### ISO 8601 Format
```
2025-11-20T11:36:57.361882Z
│    │  │  │  │  │  │      │
│    │  │  │  │  │  │      └─ UTC timezone (Z = Zulu time)
│    │  │  │  │  │  └──────── Microseconds (6 digits)
│    │  │  │  │  └─────────── Seconds
│    │  │  │  └────────────── Minutes
│    │  │  └───────────────── Hours (24-hour format)
│    │  └──────────────────── Day
│    └─────────────────────── Month
└──────────────────────────── Year
```

### Why ISO 8601?
- **Unambiguous**: No confusion about date format (MM/DD vs DD/MM)
- **Sortable**: Lexicographic sorting matches chronological sorting
- **Standard**: Widely supported by log aggregation tools
- **Machine-readable**: Easy to parse programmatically
- **Human-readable**: Still readable by developers

### Why UTC?
- **No timezone confusion**: All timestamps in same timezone
- **Distributed systems**: Services may run in different timezones
- **Daylight saving**: Avoids DST complications
- **Standard practice**: Industry standard for server logs

---

## Log Aggregation Systems

These logs work well with common log aggregation systems:

### Elasticsearch/OpenSearch
```json
{
  "@timestamp": "2025-11-20T11:36:57.361Z",
  "timestamp": "2025-11-20T11:36:57.361882Z",
  "level": "info",
  "service": "billing-service",
  "func_name": "create_subscription",
  "lineno": 123
}
```

### CloudWatch
The JSON logs can be ingested directly into CloudWatch Logs with the timestamp field parsed automatically.

### Datadog
Compatible with Datadog's log ingestion format. The `timestamp` field will be used for event ordering.

### Splunk
JSON format is natively supported. Timestamps are automatically indexed for time-based queries.

---

## Troubleshooting

### Timestamps Not Showing?

**Check environment variable**:
```bash
echo $ENVIRONMENT
# Should be "development" or not set for local development
```

**Force timestamp display**:
```python
from app.core.logging_config import setup_logging
setup_logging(log_level="INFO", json_logs=False)
```

### Function Name Showing as `<module>`?

This is expected for top-level code. For functions, it will show the actual function name:
```python
def create_subscription():
    logger.info("Creating subscription")  # func_name=create_subscription
```

### Logs Still Missing Timestamp in Production?

**Check environment**:
```bash
# Production should have:
export ENVIRONMENT=production
```

**Verify JSON output**:
```bash
# Should see JSON with "timestamp" field
python3 -c "import json; from app.core.logging_config import *; setup_logging(); get_logger('test').info('test')"
```

---

## Related Files

### Modified Files (3)
- `billing-service/app/core/logging_config.py` - Added timestamp and callsite processors
- `chat-service/app/core/logging_config.py` - Added timestamp and callsite processors
- `onboarding-service/app/core/logging_config.py` - Added timestamp and callsite processors

### Unchanged Services (Already Had Timestamps)
- `communications-service/app/core/logging_config.py` - Uses Loguru (already has timestamps)
- `workflow-service/app/core/logging_config.py` - Uses Loguru (already has timestamps)
- `answer-quality-service/app/core/logging_config.py` - Uses Loguru (already has timestamps)

---

## Best Practices

### ✅ Always Include Context
```python
logger.info(
    "Processing payment",
    tenant_id=tenant_id,      # Who?
    amount=amount,             # What?
    payment_method=method,     # How?
    timestamp_field=datetime.now()  # Don't need this - auto-added!
)
```

### ✅ Use Structured Logging
```python
# Good - structured
logger.info("Payment processed", amount=100, currency="USD")

# Avoid - unstructured
logger.info(f"Payment of ${100} USD processed")
```

### ✅ Log at Appropriate Levels
```python
logger.debug("Cache hit")              # Development debugging
logger.info("User logged in")          # Important events
logger.warning("Rate limit exceeded")  # Potential issues
logger.error("Payment failed")         # Actual errors
```

---

## Future Improvements

Possible enhancements (not currently planned):

1. **Add trace ID**: For distributed tracing across services
2. **Add hostname**: Show which server/container generated log
3. **Add custom formatters**: Allow teams to customize log format
4. **Add log rotation**: Automatic file rotation for disk-based logs
5. **Standardize all services**: Migrate all to same logging library

---

## Deployment Checklist

- [x] Update billing-service logging configuration
- [x] Update chat-service logging configuration
- [x] Update onboarding-service logging configuration
- [x] Test development mode (console logs)
- [x] Test production mode (JSON logs)
- [x] Verify timestamp format (ISO 8601)
- [x] Verify function/line info present
- [x] Create documentation
- [ ] Deploy to development environment
- [ ] Verify logs in development
- [ ] Deploy to staging environment
- [ ] Verify logs in staging
- [ ] Deploy to production environment
- [ ] Monitor logs for any issues

---

## Summary

### Problem:
- Three FastAPI services (billing, chat, onboarding) were missing timestamps in their logs
- Made debugging difficult and prevented proper event correlation

### Root Cause:
- Services used `structlog.dev.ConsoleRenderer()` without timestamp processor
- No `TimeStamper` processor configured in structlog pipeline

### Solution:
- Added `structlog.processors.TimeStamper(fmt="iso", utc=True)` to all processors
- Added `structlog.processors.CallsiteParameterAdder()` for function/line info
- Applied to both development (console) and production (JSON) configurations

### Result:
- ✅ All logs now include ISO 8601 timestamps with milliseconds
- ✅ All logs include function name and line number
- ✅ Consistent format across all six FastAPI services
- ✅ No breaking changes to existing code
- ✅ Better debugging and troubleshooting capability

---

**Fix Status**: ✅ **COMPLETE**
**Testing Status**: ✅ **VERIFIED**
**Deployment Status**: ⏳ **READY FOR DEPLOYMENT**

---

## Contact

For questions or issues related to this fix:
- Review this document
- Check the test output above
- Verify environment variables are set correctly
- Ensure services are restarted after deployment
