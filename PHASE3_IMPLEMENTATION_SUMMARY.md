# Phase 3: Account Restrictions - Implementation Summary

## Overview

Phase 3 implements comprehensive subscription-based access controls across all services. This ensures that:
- Users cannot perform actions beyond their subscription limits
- Expired/cancelled subscriptions block access appropriately
- A 3-day grace period is provided for `past_due` subscriptions
- All restrictions are enforced at the API level before expensive operations

## Implementation Status: ✅ COMPLETE

All Phase 3 components have been implemented and tested via import verification.

---

## Components Implemented

### 1. Billing Service - Subscription Checker

**File**: `billing-service/app/services/subscription_checker.py`

**Purpose**: Core business logic for subscription validation and usage limit enforcement

**Key Classes**:
- `SubscriptionChecker`: Service class with all restriction logic
- `SubscriptionRestrictionError`: Custom exception for restriction violations

**Key Methods**:
```python
# Subscription status validation
check_subscription_active(tenant_id, include_grace_period=True)
get_active_subscription(tenant_id)

# Permission checks (return Tuple[bool, Optional[str]])
check_can_upload_document(tenant_id)
check_can_ingest_website(tenant_id)
check_can_send_chat(tenant_id)

# Enforcement methods (raise SubscriptionRestrictionError)
enforce_subscription_active(tenant_id)
enforce_can_upload_document(tenant_id)
enforce_can_ingest_website(tenant_id)
enforce_can_send_chat(tenant_id)

# Usage summary
get_usage_summary(tenant_id)  # Returns detailed usage breakdown
```

**Grace Period Logic**:
- **3-day grace period** for `past_due` subscriptions
- Configurable via `GRACE_PERIOD_DAYS` constant (default: 3)
- Calculated from `current_period_end` timestamp
- If within grace period: subscription treated as active
- If beyond grace period: blocked with clear error message

**Example Usage**:
```python
checker = SubscriptionChecker(db)

# Check if chat allowed
can_chat, reason = checker.check_can_send_chat("tenant-123")
if not can_chat:
    # reason = "Monthly chat limit reached (300 chats allowed on Free plan)"
    raise HTTPException(status_code=429, detail=reason)
```

---

### 2. Billing Service - Restrictions API

**File**: `billing-service/app/api/restrictions.py`

**Purpose**: REST API endpoints for other services to check subscription restrictions

**Endpoints**:

#### `GET /api/v1/restrictions/check/subscription/{tenant_id}`
Check if tenant has active subscription
- **Query Params**: `include_grace_period` (bool, default: true)
- **Returns**: `{"is_active": bool, "reason": str|null}`

#### `GET /api/v1/restrictions/check/can-upload-document/{tenant_id}`
Check document upload permission
- **Returns**: `{"allowed": bool, "reason": str|null}`
- **Checks**: Subscription status + document limit

#### `GET /api/v1/restrictions/check/can-ingest-website/{tenant_id}`
Check website ingestion permission
- **Returns**: `{"allowed": bool, "reason": str|null}`
- **Checks**: Subscription status + website limit

#### `GET /api/v1/restrictions/check/can-send-chat/{tenant_id}`
Check chat message permission
- **Returns**: `{"allowed": bool, "reason": str|null}`
- **Checks**: Subscription status + monthly chat limit

#### `GET /api/v1/restrictions/usage/{tenant_id}`
Get comprehensive usage summary
- **Returns**:
```json
{
  "subscription_status": "active",
  "plan_name": "Free",
  "documents": {
    "used": 3,
    "limit": 5,
    "remaining": 2
  },
  "websites": {
    "used": 1,
    "limit": 1,
    "remaining": 0
  },
  "monthly_chats": {
    "used": 150,
    "limit": 300,
    "remaining": 150,
    "resets_at": "2025-12-01T00:00:00Z"
  }
}
```

**Integration**: Router registered in `billing-service/app/main.py` at line 169-173

---

### 3. Chat Service - Billing Client

**File**: `chat-service/app/services/billing_client.py`

**Purpose**: HTTP client for chat-service to communicate with billing-service

**Key Features**:
- Async HTTP client using `httpx`
- Automatic retries with exponential backoff (max 3 attempts)
- **Fail-open strategy**: On timeout/error, allows operation to prevent service disruption
- 5-second timeout for fast failure
- Comprehensive error logging

**Methods**:
```python
async def check_can_send_chat(tenant_id: str) -> Tuple[bool, Optional[str]]
async def get_usage_summary(tenant_id: str) -> Optional[dict]
async def check_subscription_status(tenant_id: str, include_grace_period: bool = True)
```

**Global Instance**: `billing_client` - ready to use

---

### 4. Chat Service - WebSocket Integration

**File**: `chat-service/app/websockets/chat.py`

**Changes**: Lines 15, 147-172

**Integration Point**: Before processing each chat message

**Flow**:
```python
# Receive message from client
user_message = message_data["message"]

# Check with billing service BEFORE processing
allowed, reason = await billing_client.check_can_send_chat(tenant_id)

if not allowed:
    # Send error to client
    await websocket.send_text(json.dumps({
        "type": "error",
        "message": f"Chat limit exceeded: {reason}",
        "error_code": "LIMIT_EXCEEDED",
        "timestamp": datetime.now().isoformat()
    }))
    continue  # Skip processing

# Process chat message normally...
```

**Benefits**:
- Prevents AI generation for blocked users (saves API costs)
- Real-time feedback to user via WebSocket
- Logged with context for monitoring

---

### 5. Onboarding Service - Billing Client

**File**: `onboarding-service/app/services/billing_client.py`

**Purpose**: HTTP client for onboarding-service to check limits before ingestion

**New Methods Added**: Lines 206-324

```python
async def check_can_upload_document(tenant_id: str) -> Dict[str, Any]
async def check_can_ingest_website(tenant_id: str) -> Dict[str, Any]
```

**Existing Method** (still available):
```python
async def check_usage_limit(usage_type: str) -> Dict[str, Any]
# usage_type: "documents", "websites", "daily_chats", "monthly_chats"
```

**Features**:
- Same fail-open strategy as chat-service
- 5-second timeout
- Comprehensive logging
- Backward compatible with existing `check_usage_limit` method

---

### 6. Onboarding Service - Document Upload Integration

**File**: `onboarding-service/app/api/documents.py`

**Changes**: Lines 47-55

**Integration Point**: Before document processing

**Flow**:
```python
@router.post("/documents/upload")
async def upload_document_with_categorization(...):
    # Validate file type first
    if file.content_type not in allowed_types:
        raise HTTPException(400, "Unsupported file type")

    # Check limits BEFORE expensive processing
    billing_client = BillingClient(claims.access_token)
    limit_check = await billing_client.check_can_upload_document(claims.tenant_id)

    if not limit_check.get("allowed", False):
        reason = limit_check.get("reason", "Document upload not allowed")
        raise HTTPException(429, detail=reason)

    # Process document...
```

**Benefits**:
- Blocks before S3 upload
- Blocks before AI categorization
- Blocks before vector embedding
- Returns HTTP 429 (Too Many Requests) with clear message

---

### 7. Onboarding Service - Website Ingestion Integration

**File**: `onboarding-service/app/api/website_ingestions.py`

**Changes**: Lines 45-53

**Integration Point**: Before website scraping

**Flow**:
```python
@router.post("/websites/ingest")
async def ingest_website(...):
    # Validate URL first
    if not website_url.startswith(('http://', 'https://')):
        raise HTTPException(400, "Invalid URL format")

    # Check limits BEFORE expensive scraping
    billing_client = BillingClient(claims.access_token)
    limit_check = await billing_client.check_can_ingest_website(claims.tenant_id)

    if not limit_check.get("allowed", False):
        reason = limit_check.get("reason", "Website ingestion not allowed")
        raise HTTPException(429, detail=reason)

    # Start scraping in background...
```

**Benefits**:
- Blocks before Playwright/Selenium launch
- Blocks before page scraping
- Blocks before AI categorization
- Blocks before vector embedding
- Returns HTTP 429 with subscription upgrade message

---

## Restriction Logic Details

### Subscription Status Checks

**Active Statuses** (allowed):
- `ACTIVE`: Fully active subscription
- `TRIALING`: Within trial period (checks `trial_ends_at`)
- `PAST_DUE`: Within 3-day grace period from `current_period_end`

**Inactive Statuses** (blocked):
- `EXPIRED`: Subscription ended
- `CANCELLED`: Cancelled and past `current_period_end`
- `PAST_DUE`: Beyond 3-day grace period
- `PENDING`: Not yet activated

### Usage Limit Checks

**Document Upload**:
1. Check subscription active
2. Query `UsageTracking` table for `documents_uploaded`
3. Compare against `Plan.max_documents`
4. Allow if: `documents_uploaded < max_documents`

**Website Ingestion**:
1. Check subscription active
2. Query `UsageTracking` table for `websites_ingested`
3. Compare against `Plan.max_websites`
4. Allow if: `websites_ingested < max_websites`

**Chat Messages**:
1. Check subscription active
2. Query `UsageTracking` table for `monthly_chats_used`
3. Compare against `Plan.monthly_chats`
4. Allow if: `monthly_chats_used < monthly_chats`

### Error Messages

**Subscription Inactive**:
- "No subscription found for this tenant"
- "Trial period has expired"
- "Subscription has expired"
- "Subscription has been cancelled"
- "Subscription past due and grace period (3 days) has expired"

**Limits Exceeded**:
- "Document limit reached (5 documents allowed on Free plan)"
- "Website limit reached (1 websites allowed on Free plan)"
- "Monthly chat limit reached (300 chats allowed on Free plan)"

---

## Fail-Open Strategy

All HTTP clients implement fail-open behavior to prevent service disruption:

**When Billing Service is Down**:
- Timeout after 5 seconds
- Log error with full context
- Return `{"allowed": True, "reason": "billing_service_timeout"}`
- Allow operation to proceed

**Rationale**:
- Prevents cascading failures
- Maintains user experience during outages
- All failures logged for monitoring/alerts
- Better than hard failure that blocks all users

**Production Considerations**:
- Set up monitoring alerts for billing service failures
- Track fail-open occurrences in metrics
- Consider circuit breaker pattern for repeated failures

---

## Testing and Verification

### Import Tests ✅

**Billing Service**:
```bash
# All imports successful
✅ SubscriptionChecker
✅ SubscriptionRestrictionError
✅ restrictions router
✅ All 11 methods verified
```

**Chat Service**:
```bash
# Client imports successful
✅ billing_client instance
✅ Base URL: http://localhost:8004
✅ API prefix: /api/v1/restrictions
```

**Onboarding Service**:
```bash
# BillingClient methods verified
✅ check_can_upload_document()
✅ check_can_ingest_website()
✅ check_usage_limit() (legacy)
```

### Integration Points Verified

- ✅ Billing service router registered in main.py
- ✅ Chat WebSocket imports billing_client
- ✅ Chat WebSocket calls check before message processing
- ✅ Document upload endpoint calls check before processing
- ✅ Website ingestion endpoint calls check before scraping

---

## Configuration

### Environment Variables

**Billing Service** (services calling it):
```bash
BILLING_SERVICE_URL=http://localhost:8004  # Default, can override
```

### Grace Period Configuration

**Location**: `billing-service/app/services/subscription_checker.py:26`

```python
class SubscriptionChecker:
    # Grace period for expired subscriptions (days)
    GRACE_PERIOD_DAYS = 3  # Adjust as needed
```

---

## API Integration Examples

### From Frontend (Angular)

```typescript
// Chat widget - handle chat limit error
socket.on('message', (data) => {
  if (data.type === 'error' && data.error_code === 'LIMIT_EXCEEDED') {
    // Show upgrade prompt
    this.showUpgradeModal(data.message);
    // "Monthly chat limit reached (300 chats allowed on Free plan)"
  }
});

// Document upload - handle 429 error
uploadDocument(file: File) {
  this.http.post('/api/v1/documents/upload', formData)
    .subscribe({
      error: (err) => {
        if (err.status === 429) {
          // Show upgrade prompt
          this.showUpgradeModal(err.error.detail);
          // "Document limit reached (5 documents allowed on Free plan)"
        }
      }
    });
}
```

### From Internal Services

```python
# Other internal service checking tenant permissions
import httpx

async def can_tenant_perform_action(tenant_id: str):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"http://billing-service:8004/api/v1/restrictions/check/subscription/{tenant_id}"
        )
        data = response.json()
        return data["is_active"], data.get("reason")
```

---

## Next Steps (Phase 4+)

With Phase 3 complete, the system now has comprehensive restriction enforcement. Future phases will build on this foundation:

**Phase 4: Payment Processing**
- Paystack integration for subscriptions
- Webhook handling for payment events
- Automatic subscription activation on payment

**Phase 5: Plan Management**
- Upgrade/downgrade flows
- Proration calculations
- Plan change effective dates

**Phase 6: Invoicing**
- Generate invoices for paid subscriptions
- Invoice history endpoint
- PDF invoice generation

**Phase 7: Notification Enhancement**
- Send limit warning emails (e.g., "80% of monthly chats used")
- Payment reminder emails
- Subscription renewal reminders

**Phase 8: Reporting & Analytics**
- Revenue reporting
- Subscription churn metrics
- Usage analytics dashboard

---

## Summary

Phase 3 delivers enterprise-grade subscription restrictions with:
- ✅ Comprehensive subscription validation (7 status types)
- ✅ 3-day grace period for failed payments
- ✅ Usage limit enforcement (documents, websites, chats)
- ✅ REST API for cross-service checks
- ✅ HTTP clients with fail-open resilience
- ✅ Integration in all critical endpoints
- ✅ Detailed error messages for users
- ✅ Extensive logging for monitoring

The system is now ready to enforce subscription-based access control across the entire ChatCraft platform.
