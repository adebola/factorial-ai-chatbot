# Billing Service 404 Error Fix

## Problem Summary

The authorization server was making requests to the billing service for subscription status but receiving **404 Not Found** errors:

```
GET /billing/admin/subscriptions/tenant/5190e7b2-04c1-477d-8dca-84462baf7bd3 → 404
```

## Root Cause

The authorization server's `BillingServiceClient.java` was calling billing service endpoints **without the `/api/v1` prefix**, while the billing service requires this prefix for all API endpoints.

### Incorrect URLs (Before)
```java
// Subscription endpoint
String url = billingServiceUrl + "/billing/admin/subscriptions/tenant/" + tenantId;
// Platform metrics endpoint
String url = billingServiceUrl + "/admin/analytics/platform-metrics";
// Revenue analytics endpoint
String url = billingServiceUrl + "/admin/analytics/revenue";
```

### Correct URLs (After)
```java
// Subscription endpoint
String url = billingServiceUrl + "/api/v1/billing/admin/subscriptions/tenant/" + tenantId;
// Platform metrics endpoint (changed to use existing dashboard endpoint)
String url = billingServiceUrl + "/api/v1/analytics/dashboard";
// Revenue analytics endpoint
String url = billingServiceUrl + "/api/v1/analytics/revenue";
```

## Changes Made

### File: `authorization-server2/src/main/java/io/factorialsystems/authorizationserver2/service/BillingServiceClient.java`

#### Change 1: Subscription Endpoint (Line 169)
**Before:**
```java
String url = billingServiceUrl + "/billing/admin/subscriptions/tenant/" + tenantId;
```

**After:**
```java
String url = billingServiceUrl + "/api/v1/billing/admin/subscriptions/tenant/" + tenantId;
```

**Impact:** Fixes 404 error when fetching tenant subscription data

---

#### Change 2: Platform Metrics Endpoint (Line 200)
**Before:**
```java
String url = billingServiceUrl + "/admin/analytics/platform-metrics";
```

**After:**
```java
String url = billingServiceUrl + "/api/v1/analytics/dashboard";
```

**Impact:**
- Fixes 404 error (the `/platform-metrics` endpoint didn't exist)
- Now uses the existing `/dashboard` endpoint which provides comprehensive platform metrics

---

#### Change 3: Revenue Analytics Endpoint (Line 231)
**Before:**
```java
String url = billingServiceUrl + "/admin/analytics/revenue";
```

**After:**
```java
String url = billingServiceUrl + "/api/v1/analytics/revenue";
```

**Impact:** Fixes 404 error when fetching revenue analytics

## Billing Service API Structure

For reference, the billing service API is structured as follows:

```
billing-service (port 8004)
│
├── /health                           # Health check (no prefix)
├── /api/v1                           # All API endpoints under this prefix
    │
    ├── /billing/admin                # Admin billing endpoints
    │   ├── /subscriptions            # List all subscriptions
    │   ├── /subscriptions/tenant/{id} # Get subscription by tenant
    │   ├── /payments                 # List all payments
    │   └── /payments/manual          # Create manual payment
    │
    ├── /analytics                    # Analytics endpoints
    │   ├── /revenue                  # Revenue metrics (MRR, ARR, growth)
    │   ├── /subscriptions            # Subscription metrics
    │   ├── /usage                    # Usage analytics
    │   ├── /payments                 # Payment analytics
    │   ├── /churn                    # Churn analysis
    │   └── /dashboard                # Comprehensive dashboard metrics
    │
    ├── /plans                        # Plan management
    │   ├── /                         # List all plans
    │   ├── /free-tier                # Get free tier plan
    │   └── /{id}                     # Get specific plan
    │
    └── /subscriptions                # Subscription operations
        ├── /                         # Create subscription
        ├── /current                  # Get current user's subscription
        └── /{id}/cancel              # Cancel subscription
```

## Testing

### Before Fix
```bash
$ curl http://localhost:8004/billing/admin/subscriptions/tenant/test-id
HTTP 404 Not Found
```

### After Fix
```bash
$ curl http://localhost:8004/api/v1/billing/admin/subscriptions/tenant/test-id
HTTP 401 Unauthorized - Authorization header missing
# ✅ 401 is correct - endpoint found, but needs authentication
```

## Verification Steps

1. **Check authorization server logs:**
   ```bash
   tail -f authorization-server2/logs/app.log
   ```
   - Should NO LONGER see 404 errors from billing service
   - May see successful responses or 401/403 errors (auth-related, not 404)

2. **Test subscription endpoint directly:**
   ```bash
   curl -v http://localhost:8004/api/v1/billing/admin/subscriptions/tenant/5190e7b2-04c1-477d-8dca-84462baf7bd3
   ```
   - Should return 401 (missing auth header), not 404

3. **Test analytics endpoints:**
   ```bash
   # Dashboard endpoint
   curl -v http://localhost:8004/api/v1/analytics/dashboard

   # Revenue endpoint
   curl -v http://localhost:8004/api/v1/analytics/revenue
   ```
   - Both should return 401 (missing auth), not 404

## Services Restarted

- ✅ **Authorization Server** - Recompiled and restarted on port 9002
- ✅ **Billing Service** - Confirmed running on port 8004

## Status

🟢 **FIXED** - All billing service endpoints are now accessible with correct paths

## Related Files

- `BillingServiceClient.java` (authorization-server2) - Fixed API paths
- `admin.py` (billing-service) - Subscription admin endpoints
- `analytics.py` (billing-service) - Analytics endpoints
- `main.py` (billing-service) - Router configuration with `/api/v1` prefix

## Next Steps

If you still see 404 errors, verify:
1. Billing service is running: `curl http://localhost:8004/health`
2. Authorization server has latest changes: `ps aux | grep authorization-server2`
3. Environment variables are set correctly (BILLING_SERVICE_URL in auth server)
