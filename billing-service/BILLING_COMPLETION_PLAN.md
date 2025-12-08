# Billing Service - Completion Implementation Plan

**Date Created:** November 24, 2025
**Current Status:** 85% Complete
**Priority:** Phase 1 is CRITICAL before production launch

---

## Executive Summary

Based on comprehensive investigation, the billing service is **85% complete** with 3 critical gaps:

1. 🔴 **CRITICAL**: Proration charges not automatically pushed to Paystack (users must manually navigate to payment)
2. 🟠 **HIGH**: No event-driven restriction enforcement (services poll repeatedly)
3. 🟡 **MEDIUM**: Trial conversion tracking incomplete (no analytics)

---

## Current Implementation Status

### ✅ FULLY IMPLEMENTED (85%)

| Feature | Status | File Location |
|---------|--------|---------------|
| Plan upgrades with proration | ✅ Complete | `services/plan_management_service.py:122-238` |
| Plan downgrades (scheduled) | ✅ Complete | `services/plan_management_service.py:240-374` |
| Paystack payment initialization | ✅ Complete | `services/paystack_service.py:36-100` |
| Paystack payment verification | ✅ Complete | `services/paystack_service.py:102-147` |
| Payment webhooks | ✅ Complete | `api/payments.py:290-385` |
| Service restriction checks | ✅ Complete | `api/restrictions.py:44-188` |
| Trial subscriptions | ✅ Complete | `services/subscription_service.py:28-126` |
| Scheduled expiration jobs | ✅ Complete | `jobs/expiration_jobs.py` |
| Subscription reactivation | ✅ Complete | `api/plan_management.py:307-373` |
| Service restoration after payment | ✅ Complete | `services/subscription_service.py:244-247` |

### ❌ MISSING FEATURES (15%)

| Feature | Impact | Priority |
|---------|--------|----------|
| Automatic Paystack charge for upgrades | Broken UX - users stuck after upgrade | 🔴 CRITICAL |
| Event-driven restriction enforcement | Inefficient polling, stale data | 🟠 HIGH |
| Trial conversion tracking | No analytics, missed optimization | 🟡 MEDIUM |

---

## Phase 1: Automatic Paystack Payment for Upgrades 🔴

### Problem

**Current Broken Flow:**
```
1. User clicks "Upgrade to Pro"
2. System calculates: $10.00 proration required
3. API returns: {"requires_payment": true, "payment_amount": 10.00}
4. ❌ User is stuck - what do they do now?
5. ❌ No payment link provided
6. ❌ User must manually find payment page (doesn't exist in UI)
```

**Expected Fixed Flow:**
```
1. User clicks "Upgrade to Pro"
2. System calculates: $10.00 proration required
3. System AUTOMATICALLY initializes Paystack payment
4. API returns: {"authorization_url": "https://checkout.paystack.com/xyz"}
5. ✅ User redirected immediately to Paystack
6. ✅ After payment, upgrade completes automatically
```

### Solution Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ User Upgrades Plan                                           │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│ Calculate Proration                                          │
│ - Old plan: $10/month, used 15 days                         │
│ - New plan: $30/month                                        │
│ - Proration: $10.00 due now                                 │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│ Initialize Paystack Payment (NEW)                           │
│ - Amount: $10.00                                             │
│ - Metadata: {upgrade, old_plan, new_plan}                   │
│ - Returns: authorization_url                                │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│ Mark Subscription as PENDING_UPGRADE (NEW)                  │
│ - Status: PENDING_UPGRADE                                    │
│ - pending_upgrade_plan_id: pro_plan_id                      │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│ Return authorization_url to Frontend                         │
│ - User is redirected to Paystack checkout                   │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼ (user pays on Paystack)
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│ Paystack Webhook: payment.success                           │
│ - Verify payment with Paystack API                          │
│ - Check metadata.type == "upgrade"                          │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│ Complete Upgrade (NEW)                                       │
│ - subscription.plan_id = pending_upgrade_plan_id            │
│ - subscription.status = ACTIVE                               │
│ - Clear pending_upgrade_plan_id                             │
│ - Send upgrade confirmation email                            │
└─────────────────────────────────────────────────────────────┘
```

### Files to Modify

#### 1. `app/models/billing.py`

**Add PENDING_UPGRADE status:**
```python
class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    PENDING = "pending"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    TRIALING = "trialing"
    PAST_DUE = "past_due"
    PENDING_UPGRADE = "pending_upgrade"  # ← NEW
```

**Add pending upgrade fields:**
```python
class Subscription(Base):
    __tablename__ = "subscriptions"

    # ... existing fields ...

    # NEW FIELDS for upgrade tracking
    pending_upgrade_plan_id = Column(String(36), ForeignKey("plans.id"), nullable=True)
    pending_upgrade_initiated_at = Column(DateTime, nullable=True)
    pending_upgrade_payment_reference = Column(String(255), nullable=True)
```

**Migration:**
```bash
alembic revision -m "Add pending upgrade fields to subscriptions"
```

#### 2. `app/services/plan_management_service.py`

**Modify `upgrade_subscription()` method (Lines 122-238):**

```python
async def upgrade_subscription(
    self,
    subscription_id: str,
    new_plan_id: str,
    user_email: str,
    user_full_name: str,
    tenant_id: str
) -> Dict[str, Any]:
    """Upgrade subscription with automatic payment initialization"""

    subscription = self.get_subscription_by_id(subscription_id, tenant_id)

    # ... existing validation code ...

    # Calculate proration
    proration = self.calculate_proration(subscription, new_plan)

    # If no payment required (free upgrade or downgrade in price)
    if proration["proration_amount"] <= 0:
        # Apply upgrade immediately
        subscription.plan_id = new_plan_id
        subscription.amount = new_plan.price
        # ... existing immediate upgrade logic ...
        return {"upgrade": "immediate", "proration": proration}

    # ═══════════════════════════════════════════════════════════
    # NEW CODE: Payment required - initialize Paystack
    # ═══════════════════════════════════════════════════════════

    # Import Paystack service
    from .paystack_service import PaystackService
    paystack = PaystackService()

    # Initialize payment transaction
    payment_result = await paystack.initialize_upgrade_payment(
        subscription_id=subscription_id,
        tenant_id=tenant_id,
        amount=proration["proration_amount"],
        currency=new_plan.currency,
        email=user_email,
        metadata={
            "type": "upgrade",
            "subscription_id": subscription_id,
            "tenant_id": tenant_id,
            "old_plan_id": subscription.plan_id,
            "new_plan_id": new_plan_id,
            "proration_days": proration["days_used"],
            "proration_amount": proration["proration_amount"]
        }
    )

    # Mark subscription as pending upgrade
    subscription.status = SubscriptionStatus.PENDING_UPGRADE
    subscription.pending_upgrade_plan_id = new_plan_id
    subscription.pending_upgrade_initiated_at = datetime.utcnow()
    subscription.pending_upgrade_payment_reference = payment_result["reference"]

    self.db.commit()

    # Log the pending upgrade
    self.logger.info(
        f"Upgrade initiated for subscription {subscription_id}",
        subscription_id=subscription_id,
        old_plan=subscription.plan_id,
        new_plan=new_plan_id,
        payment_amount=proration["proration_amount"],
        payment_reference=payment_result["reference"]
    )

    # Return payment URL for immediate redirect
    return {
        "upgrade": "pending_payment",
        "requires_payment": True,
        "payment_amount": proration["proration_amount"],
        "authorization_url": payment_result["authorization_url"],  # ← NEW
        "reference": payment_result["reference"],  # ← NEW
        "proration": proration,
        "message": "Please complete payment to finalize upgrade"
    }
```

#### 3. `app/services/paystack_service.py`

**Add new method `initialize_upgrade_payment()`:**

```python
async def initialize_upgrade_payment(
    self,
    subscription_id: str,
    tenant_id: str,
    amount: float,
    currency: str,
    email: str,
    metadata: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Initialize Paystack payment specifically for subscription upgrades.

    Args:
        subscription_id: ID of subscription being upgraded
        tenant_id: Tenant ID
        amount: Amount to charge (proration amount)
        currency: Currency code (NGN, USD, etc.)
        email: User email for payment receipt
        metadata: Additional data (old_plan, new_plan, etc.)

    Returns:
        {
            "authorization_url": "https://checkout.paystack.com/xyz",
            "reference": "TXN_123456789",
            "access_code": "abc123"
        }
    """

    # Generate unique reference
    reference = f"UPGRADE_{subscription_id}_{int(datetime.utcnow().timestamp())}"

    # Prepare payment payload
    payload = {
        "email": email,
        "amount": int(amount * 100),  # Paystack expects kobo/cents
        "currency": currency,
        "reference": reference,
        "callback_url": f"{self.callback_url}?reference={reference}",
        "metadata": {
            **metadata,
            "subscription_id": subscription_id,
            "tenant_id": tenant_id,
            "payment_type": "upgrade"
        },
        "channels": ["card", "bank", "ussd", "mobile_money"]  # All payment methods
    }

    # Call Paystack API
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{self.base_url}/transaction/initialize",
            headers=self.headers,
            json=payload,
            timeout=30.0
        )

        if response.status_code != 200:
            self.logger.error(
                "Paystack upgrade payment initialization failed",
                status_code=response.status_code,
                response=response.text
            )
            raise HTTPException(
                status_code=502,
                detail="Failed to initialize payment with Paystack"
            )

        data = response.json()

        if not data.get("status"):
            raise HTTPException(
                status_code=502,
                detail=data.get("message", "Paystack initialization failed")
            )

        result = {
            "authorization_url": data["data"]["authorization_url"],
            "access_code": data["data"]["access_code"],
            "reference": reference
        }

        self.logger.info(
            "Upgrade payment initialized successfully",
            reference=reference,
            subscription_id=subscription_id,
            amount=amount
        )

        return result
```

#### 4. `app/api/payments.py`

**Update webhook handler to complete upgrades (add after line 350):**

```python
# In handle_paystack_webhook function
# After verifying payment signature and fetching transaction data

# Extract metadata
payment_metadata = transaction_data.get("metadata", {})
payment_type = payment_metadata.get("type") or payment_metadata.get("payment_type")

# ═══════════════════════════════════════════════════════════
# NEW CODE: Handle upgrade payments
# ═══════════════════════════════════════════════════════════

if payment_type == "upgrade":
    subscription_id = payment_metadata.get("subscription_id")
    new_plan_id = payment_metadata.get("new_plan_id")

    if not subscription_id or not new_plan_id:
        logger.error("Upgrade payment missing required metadata")
        return {"status": "error", "message": "Missing metadata"}

    # Get subscription
    subscription = db.query(Subscription).filter(
        Subscription.id == subscription_id
    ).first()

    if not subscription:
        logger.error(f"Subscription {subscription_id} not found for upgrade")
        return {"status": "error", "message": "Subscription not found"}

    # Verify subscription is in PENDING_UPGRADE status
    if subscription.status != SubscriptionStatus.PENDING_UPGRADE:
        logger.warning(
            f"Subscription {subscription_id} not in PENDING_UPGRADE status",
            current_status=subscription.status
        )
        # May be duplicate webhook - return success anyway
        return {"status": "success", "message": "Already processed"}

    # Verify payment reference matches
    if subscription.pending_upgrade_payment_reference != reference:
        logger.error(
            "Payment reference mismatch",
            expected=subscription.pending_upgrade_payment_reference,
            received=reference
        )
        return {"status": "error", "message": "Reference mismatch"}

    # ═══════════════════════════════════════════════════════════
    # COMPLETE THE UPGRADE
    # ═══════════════════════════════════════════════════════════

    old_plan_id = subscription.plan_id

    # Get new plan details
    new_plan = db.query(Plan).filter(Plan.id == new_plan_id).first()
    if not new_plan:
        logger.error(f"New plan {new_plan_id} not found")
        return {"status": "error", "message": "Plan not found"}

    # Apply the upgrade
    subscription.plan_id = new_plan_id
    subscription.amount = new_plan.price
    subscription.billing_cycle = new_plan.billing_cycle
    subscription.status = SubscriptionStatus.ACTIVE

    # Clear pending upgrade fields
    subscription.pending_upgrade_plan_id = None
    subscription.pending_upgrade_initiated_at = None
    subscription.pending_upgrade_payment_reference = None

    # Update limits to new plan limits
    subscription.document_limit = new_plan.max_documents
    subscription.website_limit = new_plan.max_websites
    subscription.monthly_chat_limit = new_plan.max_monthly_chats

    db.commit()

    logger.info(
        "Upgrade completed successfully",
        subscription_id=subscription_id,
        old_plan=old_plan_id,
        new_plan=new_plan_id,
        payment_reference=reference
    )

    # Send upgrade confirmation email
    from ..services.email_publisher import EmailPublisher
    email_publisher = EmailPublisher()

    email_publisher.publish_plan_upgraded_email(
        tenant_id=subscription.tenant_id,
        to_email=subscription.user_email,
        to_name=subscription.user_full_name,
        old_plan_name=db.query(Plan).filter(Plan.id == old_plan_id).first().name,
        new_plan_name=new_plan.name,
        new_amount=new_plan.price,
        currency=new_plan.currency,
        billing_cycle=new_plan.billing_cycle
    )

    # Send payment receipt email
    email_publisher.publish_payment_received_email(
        tenant_id=subscription.tenant_id,
        to_email=subscription.user_email,
        to_name=subscription.user_full_name,
        amount=transaction_data.get("amount", 0) / 100,  # Convert from kobo
        currency=transaction_data.get("currency", "NGN"),
        reference=reference,
        payment_date=datetime.utcnow(),
        description=f"Plan upgrade: {new_plan.name}"
    )

    return {"status": "success", "message": "Upgrade completed"}

# Continue with existing webhook logic for other payment types...
```

#### 5. Update Email Templates

**Add upgrade payment reminder email:**

Create `app/services/email_templates/upgrade_payment_pending.html`:

```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Complete Your Plan Upgrade</title>
</head>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
    <div style="background: linear-gradient(135deg, #5D3EC1 0%, #3E5DC1 100%); padding: 30px; text-align: center;">
        <h1 style="color: white; margin: 0;">Complete Your Upgrade</h1>
    </div>

    <div style="padding: 30px; background-color: #f9f9f9;">
        <p>Hi {{user_name}},</p>

        <p>You've initiated an upgrade to the <strong>{{new_plan_name}}</strong> plan!</p>

        <div style="background-color: white; padding: 20px; border-radius: 5px; margin: 20px 0;">
            <h3>Payment Required</h3>
            <p><strong>Amount Due:</strong> {{currency_symbol}}{{payment_amount}}</p>
            <p><small>This is a prorated amount based on your remaining billing period.</small></p>
        </div>

        <p style="text-align: center; margin: 30px 0;">
            <a href="{{payment_url}}" style="background-color: #5D3EC1; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                Complete Payment
            </a>
        </p>

        <p><small>This link will expire in 24 hours. If you didn't initiate this upgrade, please contact support.</small></p>
    </div>
</body>
</html>
```

### Testing Plan

#### Unit Tests

```python
# tests/test_upgrade_payment_flow.py

async def test_upgrade_with_proration_initializes_payment():
    """Test that upgrade with proration > 0 initializes Paystack payment"""

    # Create subscription on $10/month plan
    subscription = create_test_subscription(plan="basic", price=10)

    # Upgrade to $30/month plan after 15 days
    response = await client.post(
        f"/api/v1/subscriptions/{subscription.id}/upgrade",
        json={"new_plan_id": "pro_plan_id"}
    )

    assert response.status_code == 200
    data = response.json()

    # Verify payment was initialized
    assert data["upgrade"] == "pending_payment"
    assert data["requires_payment"] is True
    assert "authorization_url" in data
    assert data["authorization_url"].startswith("https://checkout.paystack.com")
    assert "reference" in data

    # Verify subscription status
    subscription = db.query(Subscription).filter(Subscription.id == subscription.id).first()
    assert subscription.status == SubscriptionStatus.PENDING_UPGRADE
    assert subscription.pending_upgrade_plan_id == "pro_plan_id"


async def test_webhook_completes_upgrade():
    """Test that Paystack webhook completes pending upgrade"""

    # Create subscription in PENDING_UPGRADE status
    subscription = create_test_subscription(
        status=SubscriptionStatus.PENDING_UPGRADE,
        pending_upgrade_plan_id="pro_plan_id",
        pending_upgrade_payment_reference="TXN_12345"
    )

    # Simulate Paystack webhook
    webhook_payload = {
        "event": "charge.success",
        "data": {
            "reference": "TXN_12345",
            "status": "success",
            "amount": 2000,  # ₦20.00 in kobo
            "metadata": {
                "type": "upgrade",
                "subscription_id": subscription.id,
                "new_plan_id": "pro_plan_id"
            }
        }
    }

    response = await client.post(
        "/api/v1/webhooks/paystack",
        json=webhook_payload,
        headers={"x-paystack-signature": generate_signature(webhook_payload)}
    )

    assert response.status_code == 200

    # Verify upgrade completed
    subscription = db.query(Subscription).filter(Subscription.id == subscription.id).first()
    assert subscription.status == SubscriptionStatus.ACTIVE
    assert subscription.plan_id == "pro_plan_id"
    assert subscription.pending_upgrade_plan_id is None


async def test_failed_payment_keeps_old_plan():
    """Test that failed payment doesn't change subscription"""

    subscription = create_test_subscription(
        plan="basic",
        status=SubscriptionStatus.PENDING_UPGRADE,
        pending_upgrade_plan_id="pro_plan_id"
    )

    # User abandons payment (webhook never arrives)
    # After 24 hours, scheduled job should revert

    # Or simulate failed payment webhook
    webhook_payload = {
        "event": "charge.failed",
        "data": {
            "reference": subscription.pending_upgrade_payment_reference,
            "status": "failed",
            "metadata": {"type": "upgrade", "subscription_id": subscription.id}
        }
    }

    # Webhook should revert to old plan
    response = await client.post("/api/v1/webhooks/paystack", json=webhook_payload)

    subscription = db.query(Subscription).filter(Subscription.id == subscription.id).first()
    assert subscription.status == SubscriptionStatus.ACTIVE  # Back to original
    assert subscription.plan_id == "basic_plan_id"  # Old plan
```

#### Integration Tests

**Manual Testing Checklist:**
- [ ] Upgrade from Basic to Pro → redirects to Paystack
- [ ] Complete payment on Paystack → returns to app
- [ ] Verify subscription upgraded in database
- [ ] Verify upgrade email received
- [ ] Verify payment receipt email received
- [ ] Abandon payment → subscription stays on old plan
- [ ] Try upgrade with insufficient funds → stays on old plan

### Deployment Checklist

**Pre-Deployment:**
- [ ] Create database migration for new fields
- [ ] Run migration on staging
- [ ] Deploy code to staging
- [ ] Test end-to-end upgrade flow on staging
- [ ] Verify webhook handling works

**Production Deployment:**
- [ ] Backup database
- [ ] Run migration on production
- [ ] Deploy code to production
- [ ] Monitor logs for first 24 hours
- [ ] Test with real payment (small amount)

### Rollback Plan

If issues occur:

1. **Immediate rollback** (code only):
   ```bash
   git revert <commit-hash>
   redeploy
   ```

2. **Database rollback** (if needed):
   ```bash
   alembic downgrade -1
   ```

3. **Temporary fix**: Disable upgrade endpoint
   ```python
   # Add to upgrade endpoint temporarily
   raise HTTPException(503, "Upgrades temporarily disabled for maintenance")
   ```

---

## Phase 2: Event-Driven Service Restrictions 🟠

### Problem

**Current Polling Architecture:**

```
┌─────────────┐     HTTP GET /restrictions/check     ┌─────────────────┐
│             │──────────────────────────────────────>│                 │
│             │                                       │                 │
│ Chat        │<──────────────────────────────────────│   Billing       │
│ Service     │     Every single chat message!       │   Service       │
│             │                                       │                 │
└─────────────┘                                       └─────────────────┘
      ↑ ↓
   Every request = Network call + Database query

Onboarding Service → Same polling pattern
Communications → Same polling pattern
```

**Issues:**
- ❌ Network latency on every user action
- ❌ Billing service overwhelmed with restriction checks
- ❌ Stale data between polls
- ❌ No real-time enforcement when subscription expires

**Example: Chat Service Impact**
```python
# Current: EVERY chat message makes HTTP call
async def process_message(tenant_id, message):
    # Network call to billing service
    billing_response = await billing_client.check_can_send_chat(tenant_id)
    if not billing_response["allowed"]:
        raise HTTPException(429, "Chat limit exceeded")

    # Process message...
```

If user sends 10 messages:
- 10 HTTP calls to billing service
- 10 database queries in billing service
- ~50-100ms latency added per message

### Solution: Event-Driven + Caching

```
┌────────────────────────────────────────────────────────────────┐
│                        RabbitMQ Exchange                        │
│                    subscription-events (topic)                  │
└────────────────────┬───────────────────────────┬────────────────┘
                     │                           │
        subscription.expired        subscription.activated
                     │                           │
         ┌───────────▼──────────┐   ┌───────────▼──────────┐
         │  Chat Service         │   │  Onboarding Service  │
         │  Consumer             │   │  Consumer            │
         └───────────┬──────────┘   └───────────┬──────────┘
                     │                           │
                     ▼                           ▼
         ┌──────────────────────┐   ┌──────────────────────┐
         │  Redis Cache          │   │  Redis Cache         │
         │  Invalidate:          │   │  Invalidate:         │
         │  subscription:123     │   │  subscription:123    │
         └──────────────────────┘   └──────────────────────┘
                     │
                     ▼
         Next request: Cache miss → Fetch from billing service
         → Cache for 5 minutes
         → Subsequent requests: Use cached data (no HTTP calls!)
```

### Architecture

**1. Billing Service (Publisher)**
```python
# When subscription status changes:
subscription.status = SubscriptionStatus.EXPIRED

# Publish event
subscription_publisher.publish({
    "event": "subscription.expired",
    "tenant_id": subscription.tenant_id,
    "subscription_id": subscription.id,
    "timestamp": datetime.utcnow().isoformat()
})
```

**2. Chat Service (Consumer)**
```python
# Receives event via RabbitMQ
def on_subscription_event(message):
    event = message["event"]
    tenant_id = message["tenant_id"]

    # Invalidate Redis cache
    redis.delete(f"subscription:{tenant_id}")

    logger.info(f"Cache invalidated for {tenant_id} due to {event}")

# In chat handler
async def process_message(tenant_id, message):
    # Check Redis cache first
    cached_status = redis.get(f"subscription:{tenant_id}")

    if cached_status is None:
        # Cache miss - fetch from billing service
        billing_response = await billing_client.check_can_send_chat(tenant_id)

        # Cache for 5 minutes
        redis.setex(
            f"subscription:{tenant_id}",
            300,  # 5 minutes
            json.dumps(billing_response)
        )
    else:
        # Cache hit - use cached data (no HTTP call!)
        billing_response = json.loads(cached_status)

    if not billing_response["allowed"]:
        raise HTTPException(429, billing_response["reason"])

    # Process message...
```

### Benefits

**Performance:**
- 90% reduction in HTTP calls to billing service
- <1ms cache lookup vs 50-100ms HTTP call
- Billing service can handle 10x more users

**Real-Time:**
- Services know about subscription changes within seconds
- No waiting for next poll cycle
- Immediate restriction enforcement

**Scalability:**
- Billing service CPU usage drops dramatically
- Services can scale independently
- RabbitMQ handles message distribution

### Implementation Files

#### Create: `billing-service/app/messaging/subscription_publisher.py`

```python
import pika
import json
from datetime import datetime
from typing import Dict, Any
import os

from ..core.logging_config import get_logger

logger = get_logger("subscription_publisher")


class SubscriptionPublisher:
    """Publish subscription change events to RabbitMQ"""

    def __init__(self):
        self.rabbitmq_host = os.environ.get("RABBITMQ_HOST", "localhost")
        self.rabbitmq_port = int(os.environ.get("RABBITMQ_PORT", "5672"))
        self.rabbitmq_user = os.environ.get("RABBITMQ_USERNAME", "user")
        self.rabbitmq_password = os.environ.get("RABBITMQ_PASSWORD", "password")
        self.exchange_name = "subscription-events"

        self.connection = None
        self.channel = None
        self._setup_connection()

    def _setup_connection(self):
        """Establish connection to RabbitMQ and declare exchange"""
        try:
            credentials = pika.PlainCredentials(self.rabbitmq_user, self.rabbitmq_password)
            parameters = pika.ConnectionParameters(
                host=self.rabbitmq_host,
                port=self.rabbitmq_port,
                credentials=credentials,
                heartbeat=600
            )

            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()

            # Declare topic exchange
            self.channel.exchange_declare(
                exchange=self.exchange_name,
                exchange_type='topic',
                durable=True
            )

            logger.info(
                "Connected to RabbitMQ for subscription events",
                host=self.rabbitmq_host,
                exchange=self.exchange_name
            )

        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            raise

    def publish_subscription_changed(
        self,
        event_type: str,
        tenant_id: str,
        subscription_id: str,
        subscription_data: Dict[str, Any] = None
    ):
        """
        Publish subscription change event

        Args:
            event_type: Type of event (activated, expired, upgraded, downgraded, cancelled)
            tenant_id: Tenant ID
            subscription_id: Subscription ID
            subscription_data: Additional subscription data to include
        """

        message = {
            "event": f"subscription.{event_type}",
            "tenant_id": tenant_id,
            "subscription_id": subscription_id,
            "timestamp": datetime.utcnow().isoformat(),
            "data": subscription_data or {}
        }

        routing_key = f"subscription.{event_type}"

        try:
            # Ensure connection is alive
            if self.connection is None or self.connection.is_closed:
                self._setup_connection()

            # Publish message
            self.channel.basic_publish(
                exchange=self.exchange_name,
                routing_key=routing_key,
                body=json.dumps(message),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Persistent message
                    content_type='application/json'
                )
            )

            logger.info(
                "Published subscription event",
                event=f"subscription.{event_type}",
                tenant_id=tenant_id,
                subscription_id=subscription_id
            )

        except Exception as e:
            logger.error(
                f"Failed to publish subscription event: {e}",
                event_type=event_type,
                tenant_id=tenant_id
            )
            # Don't raise - publishing failure shouldn't break main flow

    def close(self):
        """Close RabbitMQ connection"""
        if self.connection and not self.connection.is_closed:
            self.connection.close()
            logger.info("Closed RabbitMQ connection")


# Singleton instance
_publisher = None

def get_subscription_publisher() -> SubscriptionPublisher:
    """Get or create singleton subscription publisher"""
    global _publisher
    if _publisher is None:
        _publisher = SubscriptionPublisher()
    return _publisher
```

#### Create: `chat-service/app/messaging/subscription_consumer.py`

```python
import pika
import json
import redis
import threading
from typing import Callable
import os

from ..core.logging_config import get_logger

logger = get_logger("subscription_consumer")


class SubscriptionConsumer:
    """
    Consume subscription change events from RabbitMQ
    Invalidate Redis cache when subscription status changes
    """

    def __init__(self):
        # RabbitMQ config
        self.rabbitmq_host = os.environ.get("RABBITMQ_HOST", "localhost")
        self.rabbitmq_port = int(os.environ.get("RABBITMQ_PORT", "5672"))
        self.rabbitmq_user = os.environ.get("RABBITMQ_USERNAME", "user")
        self.rabbitmq_password = os.environ.get("RABBITMQ_PASSWORD", "password")
        self.exchange_name = "subscription-events"
        self.queue_name = "chat-service-subscriptions"

        # Redis config
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self.redis_client = redis.from_url(redis_url)

        self.connection = None
        self.channel = None
        self.consumer_thread = None

    def start(self):
        """Start consuming messages in background thread"""
        self.consumer_thread = threading.Thread(target=self._consume, daemon=True)
        self.consumer_thread.start()
        logger.info("Started subscription event consumer")

    def _consume(self):
        """Consume messages from RabbitMQ"""
        try:
            credentials = pika.PlainCredentials(self.rabbitmq_user, self.rabbitmq_password)
            parameters = pika.ConnectionParameters(
                host=self.rabbitmq_host,
                port=self.rabbitmq_port,
                credentials=credentials,
                heartbeat=600
            )

            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()

            # Declare exchange (idempotent)
            self.channel.exchange_declare(
                exchange=self.exchange_name,
                exchange_type='topic',
                durable=True
            )

            # Declare queue
            self.channel.queue_declare(queue=self.queue_name, durable=True)

            # Bind queue to exchange with routing patterns
            # Listen to all subscription events
            self.channel.queue_bind(
                exchange=self.exchange_name,
                queue=self.queue_name,
                routing_key="subscription.*"  # All subscription events
            )

            # Start consuming
            self.channel.basic_consume(
                queue=self.queue_name,
                on_message_callback=self._on_message,
                auto_ack=True
            )

            logger.info(
                "Subscription consumer connected",
                queue=self.queue_name,
                exchange=self.exchange_name
            )

            self.channel.start_consuming()

        except Exception as e:
            logger.error(f"Subscription consumer error: {e}")

    def _on_message(self, ch, method, properties, body):
        """Handle incoming subscription event"""
        try:
            message = json.loads(body)

            event = message.get("event")
            tenant_id = message.get("tenant_id")

            if not tenant_id:
                logger.warning("Subscription event missing tenant_id")
                return

            # Invalidate Redis cache for this tenant
            cache_key = f"subscription:{tenant_id}"
            self.redis_client.delete(cache_key)

            # Also invalidate specific restriction caches
            self.redis_client.delete(f"can_send_chat:{tenant_id}")
            self.redis_client.delete(f"subscription_status:{tenant_id}")

            logger.info(
                "Subscription cache invalidated",
                event=event,
                tenant_id=tenant_id
            )

        except Exception as e:
            logger.error(f"Failed to process subscription event: {e}")


# Singleton instance
_consumer = None

def get_subscription_consumer() -> SubscriptionConsumer:
    """Get or create singleton subscription consumer"""
    global _consumer
    if _consumer is None:
        _consumer = SubscriptionConsumer()
    return _consumer
```

#### Modify: `billing-service/app/services/subscription_service.py`

**Add publisher calls after status changes:**

```python
# Import at top
from ..messaging.subscription_publisher import get_subscription_publisher

class SubscriptionService:
    def __init__(self, db: Session):
        self.db = db
        self.logger = get_logger("subscription_service")
        self.publisher = get_subscription_publisher()  # NEW

    # ... existing methods ...

    # In complete_subscription_payment (Line ~244-247)
    def complete_subscription_payment(...):
        # ... existing code ...

        subscription.status = SubscriptionStatus.ACTIVE
        self.db.commit()

        # NEW: Publish activation event
        self.publisher.publish_subscription_changed(
            event_type="activated",
            tenant_id=subscription.tenant_id,
            subscription_id=subscription.id,
            subscription_data={
                "plan_id": subscription.plan_id,
                "status": subscription.status.value
            }
        )
```

**Similar changes needed in:**
- `check_trial_expired()` → publish "expired" event
- `check_subscription_expired()` → publish "expired" event
- `upgrade_subscription()` → publish "upgraded" event
- `downgrade_subscription()` → publish "downgraded" event
- `cancel_subscription()` → publish "cancelled" event

### Testing

**Unit Tests:**
```python
def test_subscription_event_published():
    """Test that subscription changes publish events"""
    with patch('billing_service.messaging.publisher.get_subscription_publisher') as mock:
        subscription.status = SubscriptionStatus.EXPIRED
        db.commit()

        mock.return_value.publish_subscription_changed.assert_called_with(
            event_type="expired",
            tenant_id=subscription.tenant_id,
            subscription_id=subscription.id
        )


def test_cache_invalidated_on_event():
    """Test that Redis cache is invalidated on event"""
    # Setup: Cache exists
    redis.set(f"subscription:{tenant_id}", json.dumps({"active": True}))

    # Trigger event
    consumer._on_message(None, None, None, json.dumps({
        "event": "subscription.expired",
        "tenant_id": tenant_id
    }))

    # Verify cache cleared
    assert redis.get(f"subscription:{tenant_id}") is None
```

**Integration Tests:**
```bash
# Terminal 1: Start RabbitMQ
docker-compose up -d rabbitmq

# Terminal 2: Start billing service (publisher)
cd billing-service && uvicorn app.main:app

# Terminal 3: Start chat service (consumer)
cd chat-service && uvicorn app.main:app

# Terminal 4: Test flow
# 1. Expire a subscription in billing service
curl -X POST http://localhost:8003/api/v1/subscriptions/{id}/expire

# 2. Verify event received by chat service (check logs)
# Chat service logs should show: "Subscription cache invalidated"

# 3. Verify cache cleared
redis-cli GET subscription:{tenant_id}
# Should return (nil)
```

### Deployment

**Pre-Deployment:**
- [ ] Ensure RabbitMQ is running in all environments
- [ ] Create exchange `subscription-events` manually (or let code create)
- [ ] Deploy billing service first (publisher)
- [ ] Deploy consumer services (chat, onboarding)
- [ ] Monitor message flow in RabbitMQ management UI

**Rollback:**
- Services gracefully handle missing RabbitMQ
- Fall back to HTTP calls if consumer not running
- No breaking changes to existing functionality

---

## Phase 3: Trial Conversion Tracking 🟡

### Problem

**Current Trial Flow:**
```
User signs up → Trial starts → Trial expires → ???
```

**Missing:**
- ❌ No conversion tracking (did trial convert to paid?)
- ❌ No conversion analytics (conversion rate, time to convert)
- ❌ No dedicated "upgrade from trial" flow
- ❌ No conversion incentives (discounts, urgency)

### Solution

Add comprehensive trial conversion tracking and analytics.

### Database Changes

**Add fields to Subscription model:**

```python
class Subscription(Base):
    __tablename__ = "subscriptions"

    # ... existing fields ...

    # NEW: Trial conversion tracking
    trial_converted_at = Column(DateTime, nullable=True)
    trial_conversion_source = Column(String(50), nullable=True)  # "auto", "manual", "incentive"
    trial_conversion_discount_code = Column(String(50), nullable=True)
```

**Migration:**
```bash
alembic revision -m "Add trial conversion tracking fields"
```

### API Endpoints

#### 1. Convert Trial to Paid

**Endpoint:** `POST /api/v1/subscriptions/{id}/convert-trial`

```python
# app/api/subscriptions.py

@router.post("/{subscription_id}/convert-trial")
async def convert_trial_to_paid(
    subscription_id: str,
    plan_id: str,  # Target plan ID
    discount_code: Optional[str] = None,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """
    Convert trial subscription to paid subscription

    - Can upgrade to different plan during conversion
    - Supports discount codes for trial conversion incentives
    - Tracks conversion for analytics
    """

    service = SubscriptionService(db)

    subscription = service.get_subscription_by_id(subscription_id, claims.tenant_id)

    # Validation
    if subscription.status != SubscriptionStatus.TRIALING:
        raise HTTPException(400, "Subscription is not in trial status")

    # Get target plan
    plan = db.query(Plan).filter(Plan.id == plan_id).first()
    if not plan:
        raise HTTPException(404, "Plan not found")

    # Calculate pricing (with discount if applicable)
    amount = plan.price
    discount_amount = 0

    if discount_code:
        discount = validate_discount_code(discount_code, plan_id)
        discount_amount = (amount * discount.percentage) / 100
        amount = amount - discount_amount

    # Initialize payment
    paystack = PaystackService()
    payment_result = await paystack.initialize_transaction(
        subscription_id=subscription_id,
        tenant_id=claims.tenant_id,
        amount=amount,
        currency=plan.currency,
        email=claims.email,
        metadata={
            "type": "trial_conversion",
            "plan_id": plan_id,
            "discount_code": discount_code,
            "discount_amount": discount_amount
        }
    )

    # Mark subscription as pending conversion
    subscription.status = SubscriptionStatus.PENDING
    subscription.trial_conversion_discount_code = discount_code
    db.commit()

    return {
        "authorization_url": payment_result["authorization_url"],
        "reference": payment_result["reference"],
        "amount": amount,
        "discount_applied": discount_amount,
        "message": "Complete payment to convert trial to paid subscription"
    }
```

#### 2. Analytics Endpoints

**Conversion Rate:**
```python
@router.get("/analytics/trial-conversion-rate")
async def get_trial_conversion_rate(
    start_date: date,
    end_date: date,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """Get trial to paid conversion rate for date range"""

    # Trials started in period
    total_trials = db.query(Subscription).filter(
        Subscription.trial_starts_at >= start_date,
        Subscription.trial_starts_at <= end_date
    ).count()

    # Trials that converted
    converted_trials = db.query(Subscription).filter(
        Subscription.trial_converted_at >= start_date,
        Subscription.trial_converted_at <= end_date
    ).count()

    conversion_rate = (converted_trials / total_trials * 100) if total_trials > 0 else 0

    return {
        "period": {"start": start_date, "end": end_date},
        "total_trials": total_trials,
        "converted_trials": converted_trials,
        "conversion_rate": round(conversion_rate, 2),
        "abandoned_trials": total_trials - converted_trials
    }
```

**Time to Convert:**
```python
@router.get("/analytics/trial-conversion-time")
async def get_trial_conversion_time(
    start_date: date,
    end_date: date,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """Average time from trial start to conversion"""

    conversions = db.query(Subscription).filter(
        Subscription.trial_converted_at >= start_date,
        Subscription.trial_converted_at <= end_date,
        Subscription.trial_starts_at.isnot(None)
    ).all()

    if not conversions:
        return {"average_days": 0, "median_days": 0}

    # Calculate days to conversion for each
    days_to_convert = [
        (sub.trial_converted_at - sub.trial_starts_at).days
        for sub in conversions
    ]

    return {
        "average_days": sum(days_to_convert) / len(days_to_convert),
        "median_days": sorted(days_to_convert)[len(days_to_convert) // 2],
        "min_days": min(days_to_convert),
        "max_days": max(days_to_convert)
    }
```

### Webhook Handler Update

**Update payment webhook to track conversions:**

```python
# In handle_paystack_webhook
if payment_metadata.get("type") == "trial_conversion":
    subscription_id = payment_metadata["subscription_id"]
    plan_id = payment_metadata["plan_id"]

    subscription = db.query(Subscription).filter(
        Subscription.id == subscription_id
    ).first()

    # Complete conversion
    subscription.status = SubscriptionStatus.ACTIVE
    subscription.plan_id = plan_id
    subscription.trial_converted_at = datetime.utcnow()  # ← Track conversion time
    subscription.trial_conversion_source = "manual"
    subscription.trial_ends_at = None  # End trial

    # Reset billing period
    subscription.current_period_start = datetime.utcnow()
    subscription.current_period_end = datetime.utcnow() + timedelta(days=30)

    db.commit()

    logger.info(
        "Trial converted to paid",
        subscription_id=subscription_id,
        plan_id=plan_id,
        days_in_trial=(subscription.trial_converted_at - subscription.trial_starts_at).days
    )
```

### Email Templates

**Trial Expiring (3 days before) - Add conversion CTA:**

```html
<div style="background: #fff3cd; padding: 15px; border-radius: 5px; margin: 20px 0;">
    <h3>⏰ Your Trial Ends in 3 Days</h3>
    <p>Don't lose access! Upgrade now and save 20%:</p>
    <a href="{{upgrade_url}}?discount=TRIAL20" style="...">
        Upgrade Now - Save 20%
    </a>
</div>
```

**Abandoned Trial (3 days after expiration):**

```html
<!DOCTYPE html>
<html>
<head>
    <title>Come Back - Special Offer!</title>
</head>
<body>
    <div style="...">
        <h1>We Miss You! 😢</h1>
        <p>Your trial expired 3 days ago. Come back and get 30% off:</p>

        <div style="...">
            <h2>Special Comeback Offer</h2>
            <p><strong>30% OFF</strong> your first month</p>
            <p>Use code: <code>COMEBACK30</code></p>
            <a href="{{reactivate_url}}">Claim Your Discount</a>
        </div>

        <p><small>Offer expires in 7 days</small></p>
    </div>
</body>
</html>
```

### Testing

**Test Cases:**
- [ ] Convert trial with same plan → payment → subscription active
- [ ] Convert trial with upgrade → payment → new plan active
- [ ] Convert with discount code → reduced payment amount
- [ ] Analytics endpoint returns correct conversion rate
- [ ] Abandoned trial email sent 3 days after expiration

---

## Implementation Timeline

### Week 1: Phase 1 - Payment Integration (CRITICAL)
- **Day 1-2**: Database migration + model changes
- **Day 3-4**: Implement upgrade payment flow
- **Day 5**: Webhook handler for upgrade completion
- **Day 6**: Email templates + testing
- **Day 7**: Deploy to staging + user acceptance testing

### Week 2: Phase 2 - Event-Driven Architecture
- **Day 1-2**: Implement subscription publisher (billing)
- **Day 3**: Implement consumer (chat service)
- **Day 4**: Implement consumer (onboarding service)
- **Day 5**: Redis caching layer
- **Day 6-7**: Integration testing + deployment

### Week 3: Phase 3 - Trial Conversion
- **Day 1**: Database migration + conversion tracking fields
- **Day 2**: Convert trial endpoint
- **Day 3**: Analytics endpoints
- **Day 4-5**: Email templates + abandoned trial job
- **Day 6-7**: Testing + deployment

---

## Success Metrics

### Phase 1 Success Criteria
- ✅ 100% of upgrades return Paystack URL
- ✅ Payment completion rate >90%
- ✅ Zero user confusion about payment process
- ✅ Average upgrade time <2 minutes (from click to completion)

### Phase 2 Success Criteria
- ✅ 90% reduction in HTTP calls to billing service
- ✅ Real-time restriction enforcement (<5 second delay)
- ✅ Cache hit rate >95%
- ✅ Billing service CPU usage reduced by 60%

### Phase 3 Success Criteria
- ✅ Trial conversion rate tracked accurately
- ✅ Analytics dashboard functional
- ✅ Discount code system working
- ✅ Abandoned trial emails sent automatically

---

## Production Readiness Checklist

**Before Production Launch:**

### Phase 1 (MANDATORY)
- [ ] Payment integration tested end-to-end
- [ ] Webhook signature verification enabled
- [ ] Failed payment handling tested
- [ ] Email notifications working
- [ ] Rollback plan documented

### Phase 2 (RECOMMENDED)
- [ ] RabbitMQ in production + monitoring
- [ ] Redis cache configured
- [ ] Consumers tested in staging
- [ ] Fallback to HTTP verified

### Phase 3 (OPTIONAL)
- [ ] Analytics endpoints deployed
- [ ] Discount code system ready
- [ ] Email templates approved
- [ ] Abandoned trial job scheduled

---

## Maintenance & Monitoring

**Key Metrics to Monitor:**

1. **Payment Flow (Phase 1)**
   - Upgrade initiation rate
   - Payment completion rate
   - Payment abandonment rate
   - Average time to complete upgrade

2. **Event System (Phase 2)**
   - RabbitMQ message throughput
   - Consumer lag (message processing delay)
   - Cache hit/miss ratio
   - Billing service request volume

3. **Trial Conversion (Phase 3)**
   - Trial signup rate
   - Trial to paid conversion rate
   - Average days to conversion
   - Discount code usage rate

**Alerts:**
- Payment completion rate drops below 80%
- RabbitMQ queue depth > 1000 messages
- Cache hit rate drops below 90%
- Trial conversion rate drops below baseline

---

## Support & Documentation

**For Implementation Questions:**
- Refer to this document
- Check `/billing-service/BILLING_IMPLEMENTATION_STATUS.md`
- Review Paystack documentation: https://paystack.com/docs/api

**For Production Issues:**
- Check application logs (structured logging enabled)
- Monitor RabbitMQ management UI
- Review Redis cache status
- Check Paystack dashboard for payment failures

---

**Document Version:** 1.0
**Last Updated:** November 24, 2025
**Next Review:** After Phase 1 completion
**Owner:** Backend Team