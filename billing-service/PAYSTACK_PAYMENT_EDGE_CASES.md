# Paystack Payment Edge Case Handling Analysis

## Executive Summary

This analysis examines how the ChatCraft billing system handles edge cases during Paystack payment processing, specifically:
1. **Long-running transactions** where Paystack advises customers to return later
2. **Token expiration** during payment flows
3. **Payment completion** when users close browsers or lose connection

**Key Finding**: The system is well-architected with robust mitigations for all identified edge cases through dual-verification mechanisms, idempotency safeguards, and token-independent payment completion.

---

## Edge Case 1: Long-Running Paystack Transactions

### The Problem
Paystack transactions may take longer than expected due to:
- Bank processing delays (especially for bank transfers)
- Network timeouts
- Payment method complexity (e.g., USSD requires user to dial code)
- Paystack may show "Please check back later" message

### Current Mitigations

#### 1. Automatic Retry with Exponential Backoff
**File**: `billing-service/app/services/paystack_client.py`

```python
@retry(
    stop=stop_after_attempt(3),          # Maximum 3 attempts
    wait=wait_exponential(multiplier=1, min=1, max=10),  # 1s → 2s → 4s → max 10s
    reraise=True
)
async def verify_transaction(self, reference: str):
    # Calls Paystack API to verify payment status
```

**Impact**: If Paystack API is temporarily slow or unreachable, system automatically retries with exponential backoff (1s, 2s, 4s, up to 10s).

#### 2. HTTP Timeouts
- All async HTTP calls use `timeout=30.0` seconds
- Prevents indefinite hanging on slow API responses
- Connection pool timeout configured in database settings

#### 3. Payment Status States
**File**: `billing-service/app/models/subscription.py`

```python
class PaymentStatus(str, enum.Enum):
    PENDING = "pending"        # Initialized, awaiting user payment
    PROCESSING = "processing"  # Currently being processed
    COMPLETED = "completed"    # Successfully paid
    FAILED = "failed"          # Payment rejected
    CANCELLED = "cancelled"    # User cancelled
    REFUNDED = "refunded"      # Refunded to customer
```

**Impact**: Clear state machine prevents ambiguity. Payments stay `PENDING` until Paystack confirms completion.

#### 4. Dual-Trigger Completion Mechanism

**Path A - User Returns (Callback)**:
- User clicks back to site after payment
- `GET /api/v1/payments/callback?reference={ref}` verifies payment
- Updates database immediately
- Redirects user to success page

**Path B - Asynchronous (Webhook)**:
- Paystack sends webhook when payment completes (even if user never returns)
- `POST /api/v1/webhooks/paystack` processes payment
- Updates database independently
- Sends email confirmation

**Impact**: Payment completes successfully even if user:
- Closes browser immediately
- Loses internet connection
- Never clicks "Return to Merchant"
- Waits hours/days before returning

#### 5. Status Check Without Re-Verification
**Endpoint**: `GET /api/v1/payments/callback/status?reference={ref}`

**Feature**: No authentication required, reads status from database
**Usage**: Frontend can poll every 2-5 seconds to check status
**Impact**: User sees real-time updates without refreshing page

### Remaining Gaps

#### Gap 1: No User Notification for Long-Running Payments
**Issue**: If payment takes >5 minutes (e.g., bank transfer), user may not know it's still processing.

**Recommendation**: Add frontend polling with status updates:
```javascript
// Poll every 3 seconds for up to 5 minutes
const checkPaymentStatus = async (reference) => {
  const maxAttempts = 100; // 5 minutes
  for (let i = 0; i < maxAttempts; i++) {
    const response = await fetch(`/api/v1/payments/callback/status?reference=${reference}`);
    const data = await response.json();

    if (data.status === 'completed') {
      // Show success, redirect
      return;
    } else if (data.status === 'failed') {
      // Show error
      return;
    }

    // Show "Processing... please wait" message
    await sleep(3000);
  }
  // After 5 minutes, show "Payment processing - check email for confirmation"
};
```

#### Gap 2: No Timeout for Stuck PENDING Payments
**Issue**: Payments can remain `PENDING` indefinitely if:
- User abandons payment (doesn't complete on Paystack)
- Webhook never arrives
- User never returns to callback

**Recommendation**: Add scheduled job to mark abandoned payments:
```python
# Run every hour
def mark_abandoned_payments():
    # Find payments PENDING for >24 hours
    abandoned = db.query(Payment).filter(
        Payment.status == PaymentStatus.PENDING,
        Payment.created_at < datetime.now() - timedelta(hours=24)
    ).all()

    for payment in abandoned:
        # Try one final verification with Paystack
        result = paystack_client.verify_transaction(payment.paystack_reference)

        if result['status'] == 'abandoned':
            payment.status = PaymentStatus.CANCELLED
            payment.failure_reason = "Payment abandoned by user"
            db.commit()
```

---

## Edge Case 2: Access Token Expiration During Payment

### The Problem
JWT tokens have limited lifetime (typically 5 minutes access token, 1 hour refresh token). During payment:
1. User initiates payment (token valid)
2. Redirected to Paystack (5+ minutes)
3. Returns to site (token expired)
4. Cannot verify payment or access invoice

### Current Mitigations

#### 1. Token-Less Payment Completion
**Key Design**: Payment callback endpoints do NOT require authentication.

**Endpoint**: `GET /api/v1/payments/callback?reference={ref}`
```python
# NO TokenClaims dependency
async def payment_callback(
    reference: str = Query(...),
    db: Session = Depends(get_db)
):
    # Verifies payment using reference, not token
    await subscription_service.verify_subscription_payment(reference)
    # Redirects to frontend with reference
```

**Impact**: User's expired token doesn't prevent payment from completing.

#### 2. Webhook Independent of User Session
**Endpoint**: `POST /api/v1/webhooks/paystack`

**Authentication**: HMAC signature verification (not JWT token)
```python
def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
    expected_signature = hmac.new(
        self.secret_key.encode('utf-8'),
        payload,
        hashlib.sha512
    ).hexdigest()
    return hmac.compare_digest(expected_signature, signature)
```

**Impact**: Paystack webhook can activate subscription even if user never logs back in.

#### 3. Reference-Based Status Check
**Endpoint**: `GET /api/v1/payments/callback/status?reference={ref}`

**Feature**: No authentication required
**Use Case**: User can bookmark this URL or save reference to check later
**Impact**: User can verify payment completed even days after token expired

#### 4. Email Notifications
**File**: `billing-service/app/services/subscription_service.py` (lines 412-475)

After payment completes via webhook:
1. Sends payment receipt email with details
2. Generates invoice PDF
3. Sends invoice email with PDF attachment

**Impact**: User receives confirmation even if they never return to website.

#### 5. Token Validation with Leeway
**File**: `billing-service/app/services/dependencies.py`

```python
# 10 seconds leeway for time claims
payload = jwt.decode(
    token,
    public_key,
    algorithms=["RS256"],
    leeway=10  # Handles clock skew
)
```

**Impact**: Minor clock differences don't cause premature expiration.

### Token Flow Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Payment Initialization (REQUIRES TOKEN)                     │
│ POST /payments/initialize                                   │
│ - Validates tenant_id from token                           │
│ - Creates Payment record (PENDING)                         │
│ - Returns Paystack authorization URL                       │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ User on Paystack (NO TOKEN NEEDED)                         │
│ - User completes payment on Paystack's servers             │
│ - Token can expire here (no impact)                        │
└──────────┬───────────────────────────┬──────────────────────┘
           │                           │
           │                           │
           ▼                           ▼
┌──────────────────────┐    ┌──────────────────────────────┐
│ Callback Path        │    │ Webhook Path                 │
│ (NO TOKEN REQUIRED)  │    │ (NO TOKEN REQUIRED)          │
│                      │    │                              │
│ GET /callback        │    │ POST /webhooks/paystack      │
│ - Verifies payment   │    │ - Signature verification     │
│ - Updates DB         │    │ - Updates DB                 │
│ - Redirects user     │    │ - Sends email                │
└──────────────────────┘    └──────────────────────────────┘
```

### Remaining Gaps

#### Gap 1: Invoice Access Requires Re-Authentication
**Issue**: After payment completes, invoice endpoints require valid token:
```python
@router.get("/invoices/{invoice_id}")
async def get_invoice(
    invoice_id: str,
    claims: TokenClaims = Depends(validate_token),  # REQUIRES TOKEN
    db: Session = Depends(get_db)
):
```

**Scenario**: User completes payment, token expires, tries to download invoice → 401 Unauthorized

**Current Mitigation**: Invoice sent via email (user has PDF in inbox)

**Potential Enhancement**: Add time-limited invoice access token:
```python
# Include in payment callback redirect
invoice_token = generate_invoice_access_token(invoice_id, expires_in=3600)  # 1 hour
redirect_url = f"{FRONTEND_URL}/payment/success?invoice_token={invoice_token}"

# Add public endpoint
@router.get("/invoices/access/{invoice_token}")
async def get_invoice_by_token(invoice_token: str):
    # Verify token, return invoice without authentication
```

---

## Edge Case 3: User Closes Browser During Payment

### The Problem
User may:
1. Close browser tab while on Paystack
2. Navigate away before Paystack redirects back
3. Internet connection drops during redirect
4. Mobile app crashes

### Current Mitigations

#### 1. Webhook Ensures Completion
**Design**: Paystack sends server-to-server webhook regardless of user presence.

**File**: `billing-service/app/api/payments.py` (lines 277-392)

```python
@router.post("/webhooks/paystack")
async def handle_paystack_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    # Processes payment even if user never returned
    if event_type == "charge.success":
        await subscription_service.verify_subscription_payment(reference)
        # Updates subscription to ACTIVE
        # Generates invoice
        # Sends email confirmation
```

**Impact**: Payment completes and subscription activates automatically.

#### 2. Idempotency Protection
**File**: `billing-service/app/api/payments.py` (lines 332-350)

```python
# Check if payment already completed (via callback)
if payment and payment.status == PaymentStatus.COMPLETED:
    logger.info("Payment already completed - webhook skipped")
    paystack_service.mark_webhook_processed(webhook.id, success=True)
    return {"success": True, "message": "Payment already processed"}
```

**Impact**: If callback completes payment, webhook doesn't duplicate processing.

#### 3. Database-Unique Webhook Event IDs
**File**: `billing-service/app/models/subscription.py`

```python
class PaystackWebhook(Base):
    paystack_event_id = Column(String(255), unique=True, nullable=False, index=True)
```

**Impact**: If Paystack retries webhook (network issues), duplicate webhooks are rejected at database level.

#### 4. Email Notifications
After webhook processes payment:
- Payment receipt email sent to user
- Invoice PDF attached
- User notified via email even if they never saw success page

#### 5. Payment History Endpoint
**File**: `billing-service/app/api/payments.py`

```python
@router.get("/payments/history")
async def get_payment_history(
    claims: TokenClaims = Depends(validate_token),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    # User can see all payments when they log back in
```

**Impact**: User can verify payment completed when they return later.

### Remaining Gaps

#### Gap 1: No Frontend Notification on Re-Login
**Issue**: User closes browser, payment completes via webhook, user logs in later → doesn't know payment succeeded unless they check history.

**Recommendation**: Add "recent payment" banner on dashboard:
```python
# Add to user dashboard API
@router.get("/dashboard")
async def get_dashboard(claims: TokenClaims = Depends(validate_token)):
    # Check for payments completed in last 24 hours
    recent_payments = db.query(Payment).filter(
        Payment.tenant_id == claims.tenant_id,
        Payment.status == PaymentStatus.COMPLETED,
        Payment.processed_at > datetime.now() - timedelta(hours=24)
    ).all()

    return {
        "recent_payments": recent_payments,
        "show_success_banner": len(recent_payments) > 0
    }
```

Frontend shows: "Your payment of ₦50,000 was processed successfully! View invoice"

---

## Edge Case 4: Paystack Webhook Failures

### The Problem
Webhook may fail due to:
1. Server downtime during webhook delivery
2. Database connection issues
3. Code bugs during processing
4. Network timeouts

### Current Mitigations

#### 1. Webhook Retry from Paystack
Paystack automatically retries webhooks:
- Retry 1: Immediately
- Retry 2: After 1 minute
- Retry 3: After 5 minutes
- Continues exponentially up to 24 hours

#### 2. Webhook Logging Before Processing
**File**: `billing-service/app/services/paystack_service.py`

```python
def log_webhook_event(self, event_type, event_id, raw_data, signature):
    webhook = PaystackWebhook(
        id=str(uuid.uuid4()),
        event_type=event_type,
        paystack_event_id=event_id,
        raw_data=raw_data,
        signature=signature
    )
    self.db.add(webhook)
    self.db.commit()  # Logged even if processing fails
    return webhook
```

**Impact**: Even if processing fails, webhook is recorded for manual investigation.

#### 3. Processing Attempt Tracking
```python
webhook.processed = success
webhook.processing_attempts += 1
webhook.processed_at = datetime.now(timezone.utc)
if error:
    webhook.last_processing_error = error
self.db.commit()
```

**Impact**: Can identify webhooks that failed multiple times.

#### 4. Fallback Verification via Callback
If webhook fails but user returns to site:
- Callback endpoint verifies payment
- Updates database
- Activates subscription

**Impact**: User still gets their subscription even if all webhooks fail.

### Remaining Gaps

#### Gap 1: No Monitoring/Alerting for Failed Webhooks
**Issue**: Failed webhooks are logged but no automated alerting.

**Recommendation**: Add monitoring job:
```python
# Run every 15 minutes
def check_failed_webhooks():
    failed = db.query(PaystackWebhook).filter(
        PaystackWebhook.processed == False,
        PaystackWebhook.processing_attempts >= 3,
        PaystackWebhook.received_at > datetime.now() - timedelta(hours=6)
    ).all()

    if failed:
        # Send alert to operations team
        send_slack_alert(
            f"⚠️ {len(failed)} webhooks failed after 3+ attempts. Manual review needed."
        )
```

#### Gap 2: No Manual Webhook Replay
**Issue**: If webhook processing fails due to temporary bug, no way to manually replay.

**Recommendation**: Add admin endpoint:
```python
@router.post("/admin/webhooks/{webhook_id}/replay")
async def replay_webhook(
    webhook_id: str,
    claims: TokenClaims = Depends(require_system_admin)
):
    webhook = db.query(PaystackWebhook).get(webhook_id)
    if not webhook:
        raise HTTPException(404, "Webhook not found")

    # Reset and reprocess
    webhook.processed = False
    webhook.last_processing_error = None
    db.commit()

    # Reprocess webhook data
    await process_webhook_event(webhook.raw_data)

    return {"success": True, "message": "Webhook replayed"}
```

---

## Edge Case 5: Currency and Amount Mismatch

### Current Handling

#### Kobo Conversion
**File**: `billing-service/app/services/paystack_client.py`

```python
# Convert amount to kobo (smallest currency unit)
amount_in_kobo = int(amount * 100)
```

**Impact**: Handles decimal amounts correctly (₦50,000.50 → 5,000,050 kobo)

#### Currency Enforcement
```python
"currency": "NGN"  # Nigerian Naira hardcoded
```

**Impact**: All payments in NGN only.

### Remaining Gaps

#### Gap 1: No Multi-Currency Support
**Issue**: System only supports NGN. International customers cannot pay.

**Recommendation**: Add currency field to Plan model:
```python
class Plan(Base):
    price = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="NGN")  # ISO 4217

    # Add price_usd, price_eur for multi-currency
```

---

## Critical Files Reference

| File | Purpose | Lines |
|------|---------|-------|
| `billing-service/app/api/payments.py` | Payment endpoints | 32-392 |
| `billing-service/app/services/paystack_client.py` | Paystack API integration with retry logic | 64-313 |
| `billing-service/app/services/subscription_service.py` | Payment verification & subscription activation | 223-475 |
| `billing-service/app/models/subscription.py` | Payment & Webhook models | 113-342 |
| `billing-service/app/services/dependencies.py` | Token validation | 56-255 |

---

## Verification Steps

### Test Edge Case 1: Long Transaction
1. Initiate payment: `POST /payments/initialize`
2. On Paystack page, wait 5+ minutes before completing
3. Complete payment
4. Verify webhook processes payment (check `paystack_webhooks` table)
5. Verify subscription activated (check `subscriptions` table)
6. Verify email received

### Test Edge Case 2: Token Expiration
1. Initiate payment (save reference)
2. Wait for token expiration (>5 minutes)
3. Return to callback URL with reference
4. Verify callback still processes payment (no 401 error)
5. Verify user redirected to success page

### Test Edge Case 3: Browser Closure
1. Initiate payment
2. On Paystack page, close browser tab immediately after paying
3. Wait 1-2 minutes for webhook
4. Check database: `SELECT * FROM payments WHERE status = 'completed'`
5. Check subscription: `SELECT * FROM subscriptions WHERE status = 'active'`
6. Verify email received

### Test Edge Case 4: Webhook Failure
1. Temporarily break webhook endpoint (e.g., simulate DB error)
2. Complete payment on Paystack
3. Verify webhook logged with error
4. Return to site via callback URL
5. Verify callback completes payment despite webhook failure

---

## Summary & Recommendations

### Existing Mitigations (Strong)
✅ Dual-trigger payment completion (callback + webhook)
✅ Token-independent payment verification
✅ Automatic retry with exponential backoff
✅ Idempotency protection (multiple layers)
✅ Webhook signature verification
✅ Email notifications for offline users
✅ Payment status tracking in database
✅ Comprehensive logging for debugging

### Gaps Identified (Medium Priority)
⚠️ No frontend polling UI for long-running payments
⚠️ No abandoned payment cleanup job
⚠️ Invoice access requires re-authentication (mitigated by email)
⚠️ No dashboard banner for recent payments
⚠️ No monitoring/alerting for failed webhooks
⚠️ No manual webhook replay mechanism
⚠️ Single currency support (NGN only)

### Recommended Enhancements

**Priority 1 (High Impact, Low Effort):**
1. Add frontend payment status polling with progress indicator
2. Add scheduled job to mark abandoned payments as CANCELLED

**Priority 2 (Medium Impact, Medium Effort):**
3. Add webhook failure monitoring and Slack alerts
4. Add dashboard banner for recent successful payments
5. Add manual webhook replay endpoint for operations team

**Priority 3 (Future Enhancements):**
6. Add time-limited invoice access tokens for post-payment access
7. Multi-currency support for international customers

### Overall Assessment
**The system is well-architected for handling payment edge cases.** All critical scenarios (long transactions, token expiration, browser closure) have robust mitigations through dual-verification mechanisms and asynchronous processing. The recommended enhancements are primarily UX improvements and operational tooling, not critical security or functionality gaps.