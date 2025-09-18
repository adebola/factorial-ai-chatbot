# Shared Cache Architecture for Plan Management

## Overview

This document describes the implementation of shared Redis cache for plan management between the Authorization Server and Onboarding Service, ensuring data consistency and eliminating duplicate cache management.

## Architecture

### Before (Problems)
- **Duplicate Caching**: Both services cached the same data independently
- **Inconsistent TTLs**: Auth server (5 min) vs Onboarding (1 hour)
- **Race Conditions**: Updates might not be reflected consistently
- **Cache Key Conflicts**: Different key formats could cause issues

### After (Solution)
- **Single Source of Truth**: Onboarding service manages all plan caches
- **Read-Only Consumer**: Authorization server only reads from shared cache
- **Consistent Keys**: Standardized cache key format across services
- **Automatic Invalidation**: Cache updated on all plan CRUD operations

## Cache Key Format

All plan-related cache keys follow a consistent format:

```
plan:free_tier              # Free tier plan
plan:id:{plan_id}           # Specific plan by ID
plans:active                # All active plans
```

## Service Responsibilities

### Onboarding Service (Cache Manager)
- **READ/WRITE**: Full cache lifecycle management
- **CACHING**: Populates cache on API calls
- **INVALIDATION**: Clears cache on plan updates
- **TTL**: 1 hour (3600 seconds) for all plan data

**Key Components:**
- `CacheService`: Enhanced with plan-specific methods
- `plans.py` API: Automatic cache invalidation on CRUD operations
- `/api/v1/plans/free-tier`: Dedicated endpoint with caching

### Authorization Server (Cache Consumer)
- **READ-ONLY**: Only reads from shared cache
- **NO CACHING**: Does not write to cache
- **FALLBACK**: Calls onboarding service if cache miss
- **INTEGRATION**: Uses same cache keys as onboarding service

**Key Components:**
- `OnboardingServiceClient`: Updated to use shared cache keys
- No local caching logic (removed)
- Direct calls to `/api/v1/plans/free-tier` endpoint

## Implementation Details

### Cache Service Methods (Onboarding)

```python
# Generic cache operations
async def get(cache_key: str) -> Optional[Dict[str, Any]]
async def set(cache_key: str, data: Dict[str, Any], ttl: int = None) -> bool
async def delete(cache_key: str) -> bool

# Plan-specific operations
async def get_free_tier_plan() -> Optional[Dict[str, Any]]
async def cache_free_tier_plan(plan_data: Dict[str, Any]) -> bool
async def invalidate_free_tier_plan() -> bool
async def get_plan_by_id(plan_id: str) -> Optional[Dict[str, Any]]
async def cache_plan_by_id(plan_id: str, plan_data: Dict[str, Any]) -> bool
async def invalidate_plan_by_id(plan_id: str) -> bool
async def invalidate_all_plans_cache() -> bool
```

### Cache Invalidation Triggers

Cache is automatically invalidated when:
1. **Plan Creation**: New plan added
2. **Plan Update**: Existing plan modified
3. **Plan Deletion**: Plan soft-deleted
4. **Plan Restoration**: Deleted plan restored

### Authorization Server Integration

```java
// Modified OnboardingServiceClient.java
public JsonNode getFreeTierPlan() {
    String cacheKey = "plan:free_tier";  // Matches onboarding service

    // Try cache first (read-only)
    String cachedPlan = redisTemplate.opsForValue().get(cacheKey);
    if (cachedPlan != null && !cachedPlan.isEmpty()) {
        return objectMapper.readTree(cachedPlan);
    }

    // Call onboarding service (which will populate cache)
    return fetchFreeTierPlanFromService();
    // NO local caching here!
}
```

## Redis Configuration

Both services connect to the same Redis instance:

### Onboarding Service
```bash
REDIS_URL=redis://localhost:6379
```

### Authorization Server
```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
```

## API Flow Example

### Scenario: Get Free Tier Plan

1. **Authorization Server Request**:
   ```
   Auth Server -> Redis: GET plan:free_tier
   ```

2. **Cache Miss**:
   ```
   Auth Server -> Onboarding Service: GET /api/v1/plans/free-tier
   Onboarding Service -> Redis: GET plan:free_tier (cache miss)
   Onboarding Service -> Database: SELECT * FROM plans WHERE name='Free'
   Onboarding Service -> Redis: SET plan:free_tier {plan_data} EX 3600
   Onboarding Service -> Auth Server: {plan_data}
   ```

3. **Subsequent Cache Hit**:
   ```
   Auth Server -> Redis: GET plan:free_tier (cache hit)
   Redis -> Auth Server: {plan_data}
   ```

## Testing

### Manual Testing
```bash
# Run the test script
cd onboarding-service
python test_shared_cache.py
```

### Test Coverage
- ✅ Redis connectivity
- ✅ Cache write/read operations
- ✅ Cache key consistency
- ✅ Cache invalidation
- ✅ Service integration
- ✅ Performance verification

## Monitoring

### Log Messages
- **Cache Hits**: `"Retrieved free-tier plan from shared Redis cache"`
- **Cache Management**: `"Cached free-tier plan for 1 hour using onboarding service cache manager"`
- **Cache Invalidation**: `"Invalidated plan caches after updating plan: {plan_id}"`

### Redis Commands for Debugging
```bash
# Check if plan is cached
redis-cli GET plan:free_tier

# List all plan cache keys
redis-cli KEYS "plan:*"

# Check TTL
redis-cli TTL plan:free_tier

# Clear plan caches
redis-cli DEL plan:free_tier
redis-cli EVAL "return redis.call('del', unpack(redis.call('keys', 'plan:*')))" 0
```

## Benefits

1. **Consistency**: Single source of truth for plan data
2. **Performance**: Reduced duplicate cache operations
3. **Maintainability**: Clear separation of responsibilities
4. **Reliability**: Automatic cache invalidation on updates
5. **Scalability**: Centralized cache management

## Future Enhancements

1. **Cache Warm-up**: Pre-populate cache during service startup
2. **Cache Metrics**: Monitor cache hit/miss rates
3. **Distributed Locking**: Prevent cache stampedes
4. **Circuit Breaker**: Graceful degradation on Redis failures
5. **Cache Versioning**: Handle schema changes gracefully

## Migration Notes

### Deployment Sequence
1. Deploy onboarding service with enhanced cache service
2. Deploy authorization server with read-only cache logic
3. Verify both services use same cache keys
4. Monitor logs for cache operations

### Rollback Strategy
If issues occur, revert authorization server to original caching logic by:
1. Restoring original `OnboardingServiceClient.java`
2. Reverting to old cache key format
3. Re-enable local caching in auth server

## Conclusion

The shared cache architecture eliminates cache duplication, ensures data consistency, and provides a clear separation of responsibilities between services. The onboarding service is now the authoritative cache manager for all plan data, while the authorization server efficiently consumes cached data without managing cache lifecycle.