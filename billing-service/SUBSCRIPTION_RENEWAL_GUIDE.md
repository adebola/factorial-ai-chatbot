# Subscription Renewal Guide

## Overview

The subscription renewal feature allows users to manually renew their subscriptions before or after expiration. Renewals are **NOT automatic** - users must visit the site and initiate payment for their chosen plan.

## Key Features

- ✅ Renew ACTIVE subscriptions (extends current billing period)
- ✅ Renew EXPIRED subscriptions (reactivates with fresh period)
- ✅ Always charges FULL plan cost (no proration)
- ✅ Payment via Paystack integration
- ✅ Automatic email notifications and invoice generation
- ✅ Period extension logic based on subscription status

## How It Works

### 1. Renewal Detection (Frontend)

The Angular frontend automatically detects when a subscription is eligible for renewal:

**Renewal Button Shows When:**
- Subscription status is `EXPIRED`, OR
- Subscription status is `ACTIVE` and expiring within 7 days

**Located in:** `test-project/src/app/plans/plans.component.ts`

```typescript
shouldShowRenewal(): boolean {
  if (!this.currentSubscription) return false;

  const status = this.currentSubscription.status;

  // Show renewal for expired subscriptions
  if (status === 'expired') return true;

  // Show renewal for active subscriptions expiring soon (within 7 days)
  if (status === 'active' && this.isExpiringSoon()) return true;

  return false;
}
```

### 2. Renewal Initiation (Frontend → Backend)

When user clicks "Renew Plan":

1. **Frontend calls:** `POST /api/v1/subscriptions/{subscription_id}/renew`
2. **Backend validates:**
   - Subscription exists and belongs to tenant
   - Status is not CANCELLED or PENDING
   - No pending plan changes exist
3. **Backend calculates:**
   - Renewal amount = subscription.amount (FULL cost)
   - New period start:
     - If ACTIVE: current_period_end (extends seamlessly)
     - If EXPIRED: NOW (starts fresh)
   - New period end = new_period_start + 30 days (monthly) or 365 days (yearly)

### 3. Payment Flow

**Backend initializes Paystack payment:**

```python
# Generate unique reference
reference = f"renewal_{subscription.id}_{uuid.uuid4().hex[:8]}"

# Initialize transaction
result = await paystack.initialize_transaction(
    email=user_email,
    amount=renewal_amount,
    currency=subscription.currency,
    reference=reference,
    metadata={
        "transaction_type": "renewal",
        "new_period_start": new_period_start.isoformat(),
        "new_period_end": new_period_end.isoformat(),
        "previous_status": subscription.status.value
    }
)
```

**Frontend redirects user to Paystack:**

```typescript
// User confirms renewal
if (confirmed) {
  window.location.href = payment_url;
}
```

### 4. Payment Verification (Webhook)

When Paystack payment completes:

1. **Webhook calls:** `POST /api/v1/payments/webhook`
2. **Backend verifies payment**
3. **Backend detects TransactionType.RENEWAL**
4. **Backend updates subscription:**
   - Sets `current_period_start` = new_period_start
   - Sets `current_period_end` = new_period_end
   - Sets `ends_at` = new_period_end
   - If status was EXPIRED, changes to ACTIVE

**Located in:** `billing-service/app/services/subscription_service.py` (lines 254-383)

```python
# Handle RENEWAL transactions
if payment.transaction_type == TransactionType.RENEWAL:
    # Extract new period dates from payment metadata
    metadata = payment.payment_metadata or {}
    new_period_start = parser.isoparse(metadata.get("new_period_start"))
    new_period_end = parser.isoparse(metadata.get("new_period_end"))

    # Update subscription period
    subscription.current_period_start = new_period_start
    subscription.current_period_end = new_period_end
    subscription.ends_at = new_period_end

    # Reactivate if was EXPIRED
    if subscription.status == SubscriptionStatus.EXPIRED:
        subscription.status = SubscriptionStatus.ACTIVE
        subscription.starts_at = new_period_start
```

### 5. Post-Payment Actions

After successful payment verification:

1. **Audit Trail**: Logs renewal event
2. **Email Notification**: Sends renewal confirmation email with:
   - Renewal amount and currency
   - New period end date
   - Payment reference
3. **Invoice Generation**: Creates invoice with PDF
4. **Invoice Email**: Sends invoice to user

## API Endpoints

### Renew Subscription

**Endpoint:** `POST /api/v1/subscriptions/{subscription_id}/renew`

**Authentication:** Bearer token required

**Request:**
```json
{
  // No body required - user info extracted from JWT token
}
```

**Response:**
```json
{
  "success": true,
  "message": "Renewal payment initialized successfully",
  "renewal": {
    "subscription_id": "sub-123",
    "payment_id": "pay-456",
    "payment_url": "https://checkout.paystack.com/...",
    "payment_reference": "renewal_sub-123_abc12345",
    "amount": 999.00,
    "currency": "NGN",
    "new_period_start": "2025-01-27T10:00:00Z",
    "new_period_end": "2025-02-27T10:00:00Z"
  }
}
```

**Error Cases:**

| Status Code | Error | Reason |
|-------------|-------|--------|
| 400 | Cannot renew cancelled subscription | Status is CANCELLED |
| 400 | Cannot renew pending subscription | Status is PENDING (never activated) |
| 400 | Cannot renew with pending plan change | Has pending_plan_id scheduled |
| 403 | You can only renew your own subscriptions | Wrong tenant_id |
| 404 | Subscription not found | Invalid subscription_id |

## Period Calculation Examples

### Example 1: Renewing ACTIVE Subscription

**Current State:**
- Status: ACTIVE
- Current period: 2025-01-01 to 2025-01-31
- Today: 2025-01-25 (6 days until expiry)

**After Renewal:**
- Status: ACTIVE
- New period: 2025-01-31 to 2025-03-02 (extends from current end)
- No gap in service

### Example 2: Renewing EXPIRED Subscription

**Current State:**
- Status: EXPIRED
- Old period: 2024-12-01 to 2024-12-31
- Today: 2025-01-15 (15 days after expiry)

**After Renewal:**
- Status: ACTIVE
- New period: 2025-01-15 to 2025-02-14 (starts fresh from today)
- Subscription reactivated

## Frontend Integration

### BillingService Method

**Located in:** `test-project/src/app/services/billing.service.ts`

```typescript
renewSubscription(subscriptionId: string): Observable<RenewSubscriptionResponse> {
  return this.http.post<RenewSubscriptionResponse>(
    `${this.baseUrl}/subscriptions/${subscriptionId}/renew`,
    {},
    { headers: this.getHttpHeaders() }
  );
}
```

### PlansComponent Integration

**Located in:** `test-project/src/app/plans/plans.component.ts`

```typescript
async renewSubscription(): Promise<void> {
  if (!this.currentSubscription?.id) {
    console.error('No subscription to renew');
    return;
  }

  this.loading = true;
  this.error = null;

  try {
    const response = await this.billingService
      .renewSubscription(this.currentSubscription.id)
      .toPromise();

    if (response?.success && response.renewal) {
      const { payment_url, amount, currency, new_period_end } = response.renewal;

      // Show confirmation dialog
      const confirmed = confirm(
        `Renew your ${this.currentPlan?.name} plan?\n\n` +
        `Amount: ${currency === 'NGN' ? '₦' : '$'}${amount.toLocaleString()}\n` +
        `New expiry date: ${new Date(new_period_end).toLocaleDateString()}\n\n` +
        `You will be redirected to Paystack to complete payment.`
      );

      if (confirmed) {
        window.location.href = payment_url;
      }
    }
  } catch (error: any) {
    this.error = error.error?.detail || 'Failed to initialize renewal.';
  } finally {
    this.loading = false;
  }
}
```

### UI Template

**Located in:** `test-project/src/app/plans/plans.component.html`

```html
<!-- Renew Plan Button - shows when plan is expiring or expired -->
<button
  *ngIf="isCurrentPlan(plan) && shouldShowRenewal()"
  (click)="renewSubscription()"
  [disabled]="loading"
  class="switch-button renewal-button">
  <span *ngIf="loading" class="material-icons spinning">sync</span>
  <span *ngIf="!loading" class="material-icons">autorenew</span>
  <span *ngIf="!loading">{{ getCurrentPlanButtonLabel() }}</span>
</button>
```

## Database Schema

### Payment Model

New transaction type added:

```python
class TransactionType(str, Enum):
    SUBSCRIPTION = "subscription"
    UPGRADE = "upgrade"
    DOWNGRADE = "downgrade"
    RENEWAL = "renewal"        # New type for renewals
    REFUND = "refund"
```

### Payment Metadata Structure

For renewal transactions, metadata includes:

```python
{
    "transaction_type": "renewal",
    "old_period_end": "2025-01-31T23:59:59Z",
    "new_period_start": "2025-01-31T23:59:59Z",
    "new_period_end": "2025-03-02T23:59:59Z",
    "previous_status": "active"  # or "expired"
}
```

## Email Notifications

### Renewal Confirmation Email

**Template:** `billing-service/app/services/email_publisher.py:473-546`

**Includes:**
- Plan name
- Renewal amount and currency (₦ or $)
- New subscription period end date
- Payment reference for tracking

**Example:**
```
Subject: Your ChatCraft Pro Plan Subscription Has Been Renewed

Hello John Doe,

Great news! Your ChatCraft Pro Plan subscription has been successfully renewed.

Renewal Amount: ₦999.00
Your subscription is now active until February 27, 2025

You can continue enjoying all the features and benefits of your subscription without interruption.

Payment Reference: renewal_sub-123_abc12345

Thank you for being a valued ChatCraft customer!

Best regards,
The ChatCraft Team
```

## Testing

### Unit Tests

**Located in:** `billing-service/tests/test_subscription_renewal.py`

**Test Coverage:**
- ✅ Renew ACTIVE subscription (extends period)
- ✅ Renew EXPIRED subscription (starts fresh)
- ✅ Renew yearly subscription (365-day extension)
- ✅ Error: Cannot renew CANCELLED subscription
- ✅ Error: Cannot renew PENDING subscription
- ✅ Error: Cannot renew with pending plan change
- ✅ Error: Cannot renew wrong tenant's subscription
- ✅ Payment verification updates subscription period
- ✅ Payment verification reactivates EXPIRED subscriptions
- ✅ Renewal charges full amount (no proration)

**Run tests:**
```bash
cd billing-service
python -m pytest tests/test_subscription_renewal.py -v
```

### Manual Testing

**Test Scenario 1: Renew Active Subscription**

1. Create subscription with current_period_end in 3 days
2. Navigate to Plans page
3. Verify "Renew Plan" button appears
4. Click "Renew Plan"
5. Confirm renewal dialog
6. Complete payment on Paystack
7. Verify subscription period extended by 30 days
8. Verify renewal email received

**Test Scenario 2: Renew Expired Subscription**

1. Create subscription with current_period_end in the past
2. Update status to EXPIRED
3. Navigate to Plans page
4. Verify "Renew Plan" button appears
5. Click "Renew Plan"
6. Complete payment
7. Verify status changed to ACTIVE
8. Verify period starts from today

## Troubleshooting

### "Cannot renew subscription with pending plan change"

**Cause:** Subscription has a scheduled downgrade/upgrade

**Solution:** Wait for plan change to complete, or cancel the scheduled change before renewing

### Payment initialized but subscription not updated

**Cause:** Payment verification webhook not received or failed

**Solution:** Check Paystack webhook logs, manually verify payment using payment reference

### Renewal button not showing

**Possible Causes:**
1. Subscription not loaded (check `currentSubscription` in component)
2. More than 7 days until expiry (button only shows within 7 days)
3. Status is CANCELLED or PENDING (cannot renew these)

**Solution:** Check browser console for errors, verify subscription status in database

## Security Considerations

- ✅ Tenant isolation: Users can only renew their own subscriptions (validated via JWT tenant_id)
- ✅ Payment verification: All payments verified with Paystack before updating subscription
- ✅ Audit trail: All renewal events logged for tracking
- ✅ Idempotency: Duplicate payment attempts prevented via unique references
- ✅ Status validation: Prevents renewal of invalid subscription states

## Performance Considerations

- Renewal API calls are async and non-blocking
- Payment verification happens via webhook (decoupled from user flow)
- Email and invoice generation happens post-payment (doesn't block confirmation)
- Database queries optimized with proper indexing on subscription_id and tenant_id

## Future Enhancements

Potential improvements for future versions:

1. **Auto-renewal reminders**: Send email 7 days before expiry
2. **One-click renewal**: Store payment method for faster renewals
3. **Renewal discounts**: Offer loyalty discounts for multi-year renewals
4. **Grace period**: Allow 3-day grace period after expiry before blocking access
5. **Renewal analytics**: Track renewal rates and churn metrics

---

**Last Updated:** December 29, 2025
**Version:** 1.0.0
**Maintainer:** ChatCraft Development Team
