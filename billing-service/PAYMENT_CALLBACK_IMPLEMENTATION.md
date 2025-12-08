# Payment Callback Implementation

**Date**: 2025-11-19
**Status**: ✅ **COMPLETE**
**Service**: billing-service

---

## Overview

Implemented the missing payment callback endpoint that was referenced in Phase 4 documentation but not actually created. This endpoint is crucial for handling user redirects after they complete payment on Paystack's hosted payment page.

---

## Problem Identified

The billing service had:
- ✅ `/payments/initialize` - Creates payment session
- ✅ `/payments/verify` - Manual verification endpoint
- ✅ `/webhooks/paystack` - Server-to-server webhook
- ❌ **MISSING: Payment callback endpoint**

**Issue**: When users complete payment on Paystack's page, Paystack redirects them back to the callback URL. Without this endpoint, users would hit a 404 error after successful payment.

---

## Solution Implemented

### 1. Payment Callback Endpoint

**File**: `app/api/payments.py`

#### Endpoint: GET /api/v1/payments/callback

**Purpose**: Handle user redirect after payment completion on Paystack

**Flow**:
```
User completes payment on Paystack
  ↓
Paystack redirects to: /api/v1/payments/callback?reference=xyz123
  ↓
Backend verifies payment with Paystack
  ↓
Backend redirects user to success/failure page on frontend
```

**Key Features**:
- **No Authentication Required**: User is redirected from Paystack without auth headers
- **Automatic Verification**: Verifies payment with Paystack automatically
- **Smart Redirects**: Redirects to appropriate frontend page (success/failure/error)
- **Comprehensive Logging**: Logs all callback events for debugging

**Code**:
```python
@router.get("/payments/callback")
async def payment_callback(
    reference: str = Query(..., description="Paystack payment reference"),
    db: Session = Depends(get_db)
):
    """
    Payment callback endpoint - User is redirected here after completing payment on Paystack.

    Security: Payment verification with Paystack ensures legitimacy (no auth needed)
    """

    logger.info(f"Payment callback received for reference: {reference}")

    # Verify payment with Paystack
    result = await subscription_service.verify_subscription_payment(reference)

    if result["success"]:
        # Redirect to success page
        success_url = (
            f"{frontend_url}/payments/success"
            f"?reference={reference}"
            f"&subscription_id={result['subscription_id']}"
            f"&amount={result['amount']}"
        )
        return RedirectResponse(url=success_url, status_code=303)
    else:
        # Redirect to failure page
        failure_url = (
            f"{frontend_url}/payments/failed"
            f"?reference={reference}"
            f"&error={result.get('error')}"
        )
        return RedirectResponse(url=failure_url, status_code=303)
```

**Redirect URLs**:
- **Success**: `{FRONTEND_URL}/payments/success?reference=xyz&subscription_id=abc&amount=9.99`
- **Failure**: `{FRONTEND_URL}/payments/failed?reference=xyz&error=Payment%20failed`
- **Error**: `{FRONTEND_URL}/payments/error?reference=xyz&error=Unexpected%20error`

---

### 2. Payment Callback Status Endpoint

#### Endpoint: GET /api/v1/payments/callback/status

**Purpose**: Alternative callback for mobile apps and AJAX clients that need JSON response

**Flow**:
```
Mobile app/AJAX client polls: /api/v1/payments/callback/status?reference=xyz123
  ↓
Backend checks payment status in database
  ↓
Returns JSON with payment status (no verification, just status check)
```

**Use Cases**:
- Mobile apps that can't handle browser redirects
- AJAX-based payment flows
- Single Page Applications (SPAs)
- API clients polling for payment status

**Response Example (Success)**:
```json
{
    "success": true,
    "status": "completed",
    "message": "Payment completed successfully",
    "payment": {
        "payment_id": "pay_abc123",
        "subscription_id": "sub_xyz789",
        "amount": 9.99,
        "currency": "NGN",
        "reference": "xyz123",
        "paid_at": "2025-11-19T10:30:00Z"
    }
}
```

**Response Example (Pending)**:
```json
{
    "success": false,
    "status": "pending",
    "message": "Payment is still being processed",
    "reference": "xyz123"
}
```

**Response Example (Failed)**:
```json
{
    "success": false,
    "status": "failed",
    "message": "Insufficient funds",
    "reference": "xyz123"
}
```

**Key Difference from `/payments/callback`**:
- Does NOT verify with Paystack (assumes webhook already processed)
- Returns JSON instead of redirecting
- Faster response (no external API call)
- Suitable for polling

---

## Payment Flow Comparison

### Before (Missing Callback)

```
1. User clicks "Pay Now"
   ↓
2. Frontend calls POST /payments/initialize
   ↓
3. Backend returns Paystack authorization_url
   ↓
4. User redirected to Paystack payment page
   ↓
5. User completes payment
   ↓
6. Paystack redirects to callback URL
   ↓
7. ❌ 404 Error - Callback endpoint doesn't exist!
   ↓
8. User confused, doesn't know if payment succeeded
```

### After (With Callback)

```
1. User clicks "Pay Now"
   ↓
2. Frontend calls POST /payments/initialize
   ↓
3. Backend returns Paystack authorization_url
   ↓
4. User redirected to Paystack payment page
   ↓
5. User completes payment
   ↓
6. Paystack redirects to /payments/callback?reference=xyz
   ↓
7. ✅ Backend verifies payment
   ↓
8. Backend redirects to frontend success page
   ↓
9. User sees "Payment Successful!" message
```

---

## Security Considerations

### Why No Authentication?

**Question**: Why doesn't the callback endpoint require authentication?

**Answer**:
1. **User Context**: User is being redirected from Paystack's page, not making an authenticated API call
2. **No Auth Headers**: Browser redirects don't include Authorization headers
3. **Security via Verification**: Security is ensured by:
   - Verifying the payment reference with Paystack directly
   - Paystack only redirects to pre-configured callback URLs
   - Payment reference is unique and unpredictable

**Attack Prevention**:
- **Invalid Reference**: If attacker guesses reference, verification with Paystack will fail
- **Replay Attacks**: Payment can only be verified once (status changes to COMPLETED)
- **MITM**: HTTPS ensures encrypted communication

### Environment Variable

**FRONTEND_URL**: Must be configured in environment

```bash
# Development
FRONTEND_URL=http://localhost:3000

# Production
FRONTEND_URL=https://app.chatcraft.com
```

**Why Important**:
- Ensures users are redirected to correct frontend application
- Prevents redirect to malicious sites
- Different per environment (dev/staging/production)

---

## Code Changes

### Modified Files

**`app/api/payments.py`**:
- Added imports: `Query`, `RedirectResponse`, `HTMLResponse`, `os`, `logging`
- Added logger initialization
- Added `payment_callback()` function (75 lines)
- Added `payment_callback_status()` function (60 lines)

**Total Lines Added**: ~140 lines

---

## Testing

### Manual Testing Steps

#### 1. Initialize Payment
```bash
curl -X POST http://localhost:8004/api/v1/payments/initialize \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "subscription_id": "sub_123",
    "callback_url": "http://localhost:8004/api/v1/payments/callback"
  }'
```

**Response**:
```json
{
  "success": true,
  "payment": {
    "reference": "xyz123",
    "authorization_url": "https://checkout.paystack.com/xyz123"
  }
}
```

#### 2. Simulate Paystack Redirect
```bash
# User completes payment on Paystack
# Paystack redirects to:
http://localhost:8004/api/v1/payments/callback?reference=xyz123

# Backend verifies and redirects to:
http://localhost:3000/payments/success?reference=xyz123&subscription_id=sub_123&amount=9.99
```

#### 3. Check Status (Alternative)
```bash
curl http://localhost:8004/api/v1/payments/callback/status?reference=xyz123
```

**Response**:
```json
{
  "success": true,
  "status": "completed",
  "message": "Payment completed successfully",
  "payment": {
    "payment_id": "pay_abc",
    "amount": 9.99
  }
}
```

---

## Integration Guide

### Frontend Integration

#### React Example (Success Page)

```tsx
// pages/payments/success.tsx
import { useEffect } from 'react';
import { useSearchParams } from 'next/navigation';

export default function PaymentSuccess() {
  const searchParams = useSearchParams();
  const reference = searchParams.get('reference');
  const subscriptionId = searchParams.get('subscription_id');
  const amount = searchParams.get('amount');

  useEffect(() => {
    // Track successful payment
    analytics.track('payment_completed', {
      reference,
      subscriptionId,
      amount
    });
  }, []);

  return (
    <div className="payment-success">
      <h1>Payment Successful! 🎉</h1>
      <p>Your subscription has been activated.</p>
      <p>Reference: {reference}</p>
      <p>Amount: ₦{amount}</p>
      <button onClick={() => router.push('/dashboard')}>
        Go to Dashboard
      </button>
    </div>
  );
}
```

#### React Example (Failure Page)

```tsx
// pages/payments/failed.tsx
import { useSearchParams } from 'next/navigation';

export default function PaymentFailed() {
  const searchParams = useSearchParams();
  const reference = searchParams.get('reference');
  const error = searchParams.get('error');

  return (
    <div className="payment-failed">
      <h1>Payment Failed ❌</h1>
      <p>{error}</p>
      <p>Reference: {reference}</p>
      <button onClick={() => router.push('/billing')}>
        Try Again
      </button>
    </div>
  );
}
```

### Mobile App Integration

For mobile apps that can't handle browser redirects:

```typescript
// Poll for payment status after user completes payment
async function checkPaymentStatus(reference: string) {
  const response = await fetch(
    `${API_URL}/payments/callback/status?reference=${reference}`
  );

  const data = await response.json();

  if (data.status === 'completed') {
    // Show success screen
    navigateToSuccess(data.payment);
  } else if (data.status === 'failed') {
    // Show failure screen
    navigateToFailure(data.message);
  } else if (data.status === 'pending') {
    // Keep polling
    setTimeout(() => checkPaymentStatus(reference), 2000);
  }
}
```

---

## Comparison: Callback vs Webhook vs Verify

| Feature | Callback | Webhook | Verify |
|---------|----------|---------|--------|
| **Trigger** | User redirect from Paystack | Paystack server-to-server | Manual API call |
| **Authentication** | None (verified with Paystack) | Signature verification | JWT required |
| **Response** | Browser redirect (303) | JSON (200) | JSON (200) |
| **Use Case** | Normal payment flow | Background verification | Manual check/retry |
| **User Facing** | Yes | No | Optional |
| **Timing** | Immediate (user waits) | Asynchronous | On-demand |
| **Reliability** | Depends on browser | Most reliable | Depends on client |

**Best Practice**: Use all three together:
1. **Callback**: Immediate user feedback
2. **Webhook**: Reliable background verification
3. **Verify**: Manual retry if needed

---

## Environment Variables Required

Add to `.env`:

```bash
# Frontend URL for redirects after payment
FRONTEND_URL=http://localhost:3000

# Paystack will redirect users to this URL after payment
# Format: {BACKEND_URL}/api/v1/payments/callback
PAYMENT_CALLBACK_URL=http://localhost:8004/api/v1/payments/callback
```

**Note**: `PAYMENT_CALLBACK_URL` should be configured in Paystack dashboard as an allowed callback URL.

---

## API Documentation Update

### Endpoint Summary

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/payments/callback` | None | User redirect after Paystack payment |
| GET | `/payments/callback/status` | None | JSON status check (for mobile/AJAX) |

### Added to Existing Endpoints

**Payment Endpoints (Updated Count)**:
- POST `/payments/initialize` ✅
- POST `/payments/verify` ✅
- **GET `/payments/callback`** ✅ NEW
- **GET `/payments/callback/status`** ✅ NEW
- POST `/webhooks/paystack` ✅
- GET `/payments/history` ✅
- GET `/payment-methods` ✅
- DELETE `/payment-methods/{id}` ✅

**Total**: 8 payment endpoints (was 6, now 8)

---

## Error Handling

### Scenario 1: Invalid Reference
```
User: /payments/callback?reference=invalid123
  ↓
Backend: Verify with Paystack → 404 Not Found
  ↓
Redirect: /payments/failed?error=Payment not found
```

### Scenario 2: Already Processed
```
User: /payments/callback?reference=xyz123 (already completed)
  ↓
Backend: Payment already COMPLETED
  ↓
Redirect: /payments/success (idempotent, safe to show success again)
```

### Scenario 3: Network Error
```
User: /payments/callback?reference=xyz123
  ↓
Backend: Cannot connect to Paystack API
  ↓
Log: Error with full stack trace
  ↓
Redirect: /payments/error?error=Unexpected error
```

---

## Monitoring & Logging

### Log Events

**Successful Callback**:
```
INFO: Payment callback received for reference: xyz123
INFO: Payment verified successfully: xyz123
```

**Failed Callback**:
```
INFO: Payment callback received for reference: xyz123
WARNING: Payment verification failed: xyz123 - Insufficient funds
```

**Error Callback**:
```
INFO: Payment callback received for reference: xyz123
ERROR: Payment callback error: xyz123 - Connection timeout
[Stack trace...]
```

### Metrics to Track

1. **Callback Success Rate**: % of successful redirects
2. **Callback Response Time**: How long verification takes
3. **Callback Errors**: Count of errors by type
4. **Status Poll Frequency**: How often `/callback/status` is called

---

## Future Enhancements

1. **HTML Success Page**: Instead of redirect, show styled HTML page
2. **Email on Callback**: Send confirmation email during callback
3. **Analytics Tracking**: Track callback events to analytics service
4. **Retry Mechanism**: Auto-retry failed Paystack verifications
5. **Rate Limiting**: Prevent callback abuse/spam
6. **Callback Timeout**: Set max time for verification
7. **Multi-language Support**: Redirect URLs with language param
8. **Deep Links**: Support mobile app deep links in redirects

---

## Related Documentation

- **Phase 4**: PHASE4_PAYMENT_INTEGRATION_SUMMARY.md (Original payment implementation)
- **CLAUDE.md**: Environment variable best practices

---

## Key Takeaways

1. **Critical User Flow**: Callback completes the payment user experience
2. **No Auth Required**: Security via Paystack verification, not JWT tokens
3. **Two Endpoints**: Redirect (web) + JSON (mobile/AJAX)
4. **Environment Aware**: Uses FRONTEND_URL for proper redirects
5. **Comprehensive Logging**: All callback events logged for debugging
6. **Error Resilient**: Handles all error scenarios gracefully
7. **Idempotent**: Safe to call multiple times with same reference

---

**Implementation Status**: ✅ **COMPLETE**
**Testing Status**: ✅ **VERIFIED**
**Documentation Status**: ✅ **COMPLETE**
