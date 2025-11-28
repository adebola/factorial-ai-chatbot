# Complete Payment & Subscription Management Implementation Plan

**Date:** 2025-11-08
**Status:** Planning Phase
**Priority:** High

---

## Executive Summary

This plan implements a complete payment and subscription management system for FactorialBot with the following requirements:

1. ✅ **14-Day Trial on Registration** - All new users get Basic plan trial
2. ✅ **Immediate Restriction After Trial** - Hard stop when trial expires
3. ✅ **Manual Renewal Workflow** - Users must return to platform to renew (no auto-charge)
4. ✅ **Paid Basic Plan** - Basic costs NGN 50,000/month after trial
5. ✅ **Email Notifications** - 3 days before trial, on expiration, 7 days before renewal
6. ✅ **Industry Best Practices** - Proration, scheduled downgrades, proper status management

---

## Current State Analysis

### ✅ What Already Exists

1. **Full Paystack Integration** (`billing-service/app/services/paystack_service.py`)
   - Payment initialization, verification, refunds
   - Webhook signature verification
   - Customer and authorization management

2. **Subscription Management** (`billing-service/app/services/subscription_service.py`)
   - Create subscriptions with trials
   - Plan upgrades with proration
   - Scheduled downgrades (at period end)
   - Usage tracking integration

3. **Usage Limit Enforcement** (partially)
   - Document upload checks limits
   - Website ingestion checks limits
   - Chat service checks limits with Redis caching
   - RabbitMQ event-driven usage tracking

4. **Payment Endpoints**
   - `POST /api/v1/payments/initialize` - Start payment
   - `POST /api/v1/payments/verify` - Verify payment
   - `POST /api/v1/webhooks/paystack` - Handle webhooks

5. **Database Schema**
   - Plans, subscriptions, payments, invoices
   - Usage tracking, payment methods
   - Subscription change audit trail

### ❌ Critical Gaps

1. **NO Trial/Subscription Expiration Enforcement**
   - Limit checks don't verify subscription status
   - No automatic status changes (TRIALING → EXPIRED)
   - Users can continue using service after trial/subscription expires

2. **NO Background Jobs**
   - No scheduled task runner (APScheduler/Celery)
   - No automated expiration checks
   - No automated email notifications

3. **NO Email Notification System**
   - No trial expiring reminders
   - No subscription expiring reminders
   - No payment success confirmations

4. **NO Renewal Workflow**
   - Payment flow exists but no renewal-specific logic
   - No usage counter resets on renewal
   - No period date updates on renewal

---

## Implementation Plan

## Phase 1: Database & Model Updates

### 1.1 Add EXPIRED Status to Enum

**File:** `billing-service/app/models/subscription.py`

```python
class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    PENDING = "pending"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"
    EXPIRED = "expired"      # ADD THIS
    TRIALING = "trialing"
```

### 1.2 Create Notification Tracking Table

**New Alembic Migration:** `add_notification_logs_table.py`

```python
op.create_table(
    'notification_logs',
    sa.Column('id', sa.String(36), primary_key=True),
    sa.Column('tenant_id', sa.String(36), nullable=False, index=True),
    sa.Column('subscription_id', sa.String(36), nullable=False),
    sa.Column('notification_type', sa.String(50), nullable=False),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('email_to', sa.String(255), nullable=False),
    sa.Column('subject', sa.String(255), nullable=False),
    sa.Column('status', sa.String(20), nullable=False),  # sent, failed
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now())
)
```

**Notification Types:**
- `trial_expiring_soon` (3 days before)
- `trial_expired` (on expiration)
- `subscription_expiring_soon` (7 days before)
- `subscription_expired` (on expiration)
- `payment_successful`
- `subscription_renewed`

---

## Phase 2: Background Job System (APScheduler)

### 2.1 Install Dependencies

**File:** `billing-service/requirements.txt`

```
APScheduler==3.10.4
```

### 2.2 Create Scheduler Configuration

**File:** `billing-service/app/core/scheduler.py`

```python
"""
APScheduler configuration for background jobs
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import logging

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()

def start_scheduler():
    """Initialize and start the scheduler"""
    from ..jobs.subscription_jobs import (
        check_trial_expirations,
        check_subscription_expirations,
        send_trial_reminders,
        send_subscription_reminders
    )

    # Check trial expirations every hour
    scheduler.add_job(
        check_trial_expirations,
        trigger=IntervalTrigger(hours=1),
        id='check_trial_expirations',
        name='Check trial expirations',
        replace_existing=True
    )

    # Check subscription expirations daily at midnight
    scheduler.add_job(
        check_subscription_expirations,
        trigger=CronTrigger(hour=0, minute=0),
        id='check_subscription_expirations',
        name='Check subscription expirations',
        replace_existing=True
    )

    # Send trial reminders daily at 10 AM
    scheduler.add_job(
        send_trial_reminders,
        trigger=CronTrigger(hour=10, minute=0),
        id='send_trial_reminders',
        name='Send trial expiring reminders',
        replace_existing=True
    )

    # Send subscription reminders daily at 10 AM
    scheduler.add_job(
        send_subscription_reminders,
        trigger=CronTrigger(hour=10, minute=0),
        id='send_subscription_reminders',
        name='Send subscription expiring reminders',
        replace_existing=True
    )

    scheduler.start()
    logger.info("✅ Scheduler started successfully")

def shutdown_scheduler():
    """Shutdown the scheduler gracefully"""
    scheduler.shutdown()
    logger.info("Scheduler shutdown")
```

### 2.3 Create Scheduled Jobs Module

**File:** `billing-service/app/jobs/__init__.py`

```python
"""Background jobs for subscription management"""
```

**File:** `billing-service/app/jobs/subscription_jobs.py`

```python
"""
Scheduled jobs for subscription management
"""
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import and_
from ..core.database import SessionLocal
from ..models.subscription import Subscription, SubscriptionStatus
from ..services.email_service import send_trial_expiring_email, send_trial_expired_email
from ..services.email_service import send_subscription_expiring_email, send_subscription_expired_email

logger = logging.getLogger(__name__)

def check_trial_expirations():
    """
    Check for expired trials and update subscription status.
    Runs every hour.
    """
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)

        # Find all TRIALING subscriptions where trial has expired
        expired_trials = db.query(Subscription).filter(
            and_(
                Subscription.status == SubscriptionStatus.TRIALING,
                Subscription.trial_ends_at <= now
            )
        ).all()

        count = 0
        for subscription in expired_trials:
            # Update status to EXPIRED
            subscription.status = SubscriptionStatus.EXPIRED

            # Send trial expired email
            try:
                send_trial_expired_email(subscription.tenant_id, subscription.id)
            except Exception as e:
                logger.error(f"Failed to send trial expired email: {e}")

            count += 1

        db.commit()
        logger.info(f"✅ Checked trial expirations: {count} trials expired")

    except Exception as e:
        db.rollback()
        logger.error(f"❌ Error checking trial expirations: {e}", exc_info=True)
    finally:
        db.close()

def check_subscription_expirations():
    """
    Check for expired subscriptions and update status.
    Runs daily at midnight.
    """
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)

        # Find all ACTIVE subscriptions where period has expired
        expired_subs = db.query(Subscription).filter(
            and_(
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.ends_at <= now
            )
        ).all()

        count = 0
        for subscription in expired_subs:
            # Update status to EXPIRED
            subscription.status = SubscriptionStatus.EXPIRED

            # Send subscription expired email
            try:
                send_subscription_expired_email(subscription.tenant_id, subscription.id)
            except Exception as e:
                logger.error(f"Failed to send subscription expired email: {e}")

            count += 1

        db.commit()
        logger.info(f"✅ Checked subscription expirations: {count} subscriptions expired")

    except Exception as e:
        db.rollback()
        logger.error(f"❌ Error checking subscription expirations: {e}", exc_info=True)
    finally:
        db.close()

def send_trial_reminders():
    """
    Send reminders for trials expiring in 3 days.
    Runs daily at 10 AM.
    """
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        reminder_date = now + timedelta(days=3)

        # Find trials expiring in 3 days (within 24-hour window)
        trials_expiring_soon = db.query(Subscription).filter(
            and_(
                Subscription.status == SubscriptionStatus.TRIALING,
                Subscription.trial_ends_at >= reminder_date,
                Subscription.trial_ends_at < reminder_date + timedelta(days=1)
            )
        ).all()

        count = 0
        for subscription in trials_expiring_soon:
            try:
                # Check if we already sent this notification
                from ..models.notification import NotificationLog
                already_sent = db.query(NotificationLog).filter(
                    and_(
                        NotificationLog.subscription_id == subscription.id,
                        NotificationLog.notification_type == 'trial_expiring_soon'
                    )
                ).first()

                if not already_sent:
                    send_trial_expiring_email(subscription.tenant_id, subscription.id)
                    count += 1
            except Exception as e:
                logger.error(f"Failed to send trial expiring email: {e}")

        logger.info(f"✅ Sent {count} trial expiring reminders")

    except Exception as e:
        logger.error(f"❌ Error sending trial reminders: {e}", exc_info=True)
    finally:
        db.close()

def send_subscription_reminders():
    """
    Send reminders for subscriptions expiring in 7 days.
    Runs daily at 10 AM.
    """
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        reminder_date = now + timedelta(days=7)

        # Find subscriptions expiring in 7 days (within 24-hour window)
        subs_expiring_soon = db.query(Subscription).filter(
            and_(
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.ends_at >= reminder_date,
                Subscription.ends_at < reminder_date + timedelta(days=1)
            )
        ).all()

        count = 0
        for subscription in subs_expiring_soon:
            try:
                # Check if we already sent this notification
                from ..models.notification import NotificationLog
                already_sent = db.query(NotificationLog).filter(
                    and_(
                        NotificationLog.subscription_id == subscription.id,
                        NotificationLog.notification_type == 'subscription_expiring_soon'
                    )
                ).first()

                if not already_sent:
                    send_subscription_expiring_email(subscription.tenant_id, subscription.id)
                    count += 1
            except Exception as e:
                logger.error(f"Failed to send subscription expiring email: {e}")

        logger.info(f"✅ Sent {count} subscription expiring reminders")

    except Exception as e:
        logger.error(f"❌ Error sending subscription reminders: {e}", exc_info=True)
    finally:
        db.close()
```

### 2.4 Integrate Scheduler into Application

**File:** `billing-service/app/main.py`

```python
# Add import
from .core.scheduler import start_scheduler, shutdown_scheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info("Starting Billing Service...")

    # ... existing startup code ...

    # Start scheduler
    try:
        start_scheduler()
        logger.info("✅ Background scheduler started")
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")
        logger.warning("Service will continue but scheduled jobs will not run")

    yield

    # Shutdown
    logger.info("Shutting down Billing Service...")

    # ... existing shutdown code ...

    # Stop scheduler
    try:
        shutdown_scheduler()
        logger.info("Background scheduler stopped")
    except Exception as e:
        logger.error(f"Error stopping scheduler: {e}")
```

---

## Phase 3: Enhanced Limit Checking (Account Restrictions)

### 3.1 Modify Usage Check Endpoint

**File:** `billing-service/app/api/usage.py`

**Update the `check_usage_limit()` function:**

```python
@router.get("/check/{usage_type}", response_model=LimitCheckResponse)
async def check_usage_limit(
    usage_type: str,
    claims: TokenClaims = Depends(validate_token_or_api_key),
    db: Session = Depends(get_db)
) -> LimitCheckResponse:
    """
    Check if tenant can perform an action based on usage limits.

    NOW INCLUDES: Subscription status validation and expiration checks
    """

    try:
        subscription_service = SubscriptionService(db)
        plan_service = PlanService(db)

        # Get current subscription and plan
        subscription = subscription_service.get_subscription_by_tenant(claims.tenant_id)
        if not subscription:
            return LimitCheckResponse(
                allowed=False,
                usage_type=usage_type,
                current_usage=0,
                limit=0,
                remaining=0,
                unlimited=False,
                reason="No active subscription found"
            )

        # ========== NEW: SUBSCRIPTION STATUS CHECKS ==========
        now = datetime.now(timezone.utc)

        # Check 1: If already EXPIRED, block immediately
        if subscription.status == SubscriptionStatus.EXPIRED:
            return LimitCheckResponse(
                allowed=False,
                usage_type=usage_type,
                current_usage=0,
                limit=0,
                remaining=0,
                unlimited=False,
                reason="subscription_expired"
            )

        # Check 2: Auto-expire trials that have ended
        if subscription.status == SubscriptionStatus.TRIALING:
            if subscription.trial_ends_at and now > subscription.trial_ends_at:
                # Auto-update status
                subscription.status = SubscriptionStatus.EXPIRED
                db.commit()

                return LimitCheckResponse(
                    allowed=False,
                    usage_type=usage_type,
                    current_usage=0,
                    limit=0,
                    remaining=0,
                    unlimited=False,
                    reason="trial_expired"
                )

        # Check 3: Auto-expire subscriptions that have ended
        if subscription.status == SubscriptionStatus.ACTIVE:
            if subscription.ends_at and now > subscription.ends_at:
                # Auto-update status
                subscription.status = SubscriptionStatus.EXPIRED
                db.commit()

                return LimitCheckResponse(
                    allowed=False,
                    usage_type=usage_type,
                    current_usage=0,
                    limit=0,
                    remaining=0,
                    unlimited=False,
                    reason="subscription_expired"
                )

        # Check 4: PENDING subscriptions cannot use resources
        if subscription.status == SubscriptionStatus.PENDING:
            return LimitCheckResponse(
                allowed=False,
                usage_type=usage_type,
                current_usage=0,
                limit=0,
                remaining=0,
                unlimited=False,
                reason="payment_required"
            )

        # ========== EXISTING USAGE LIMIT CHECKS ==========
        plan = plan_service.get_plan_by_id(subscription.plan_id)
        if not plan:
            return LimitCheckResponse(
                allowed=False,
                usage_type=usage_type,
                current_usage=0,
                limit=0,
                remaining=0,
                unlimited=False,
                reason="Plan not found"
            )

        # Get usage tracking
        usage = db.query(UsageTracking).filter(
            UsageTracking.subscription_id == subscription.id
        ).first()

        if not usage:
            subscription_service._initialize_usage_tracking(subscription)
            usage = db.query(UsageTracking).filter(
                UsageTracking.subscription_id == subscription.id
            ).first()

        # Check limits based on usage type
        if usage_type == "documents":
            current = usage.documents_used
            limit = plan.document_limit
            allowed = (limit == -1) or (current < limit)
        elif usage_type == "websites":
            current = usage.websites_used
            limit = plan.website_limit
            allowed = (limit == -1) or (current < limit)
        elif usage_type == "daily_chats":
            current = usage.daily_chats_used
            limit = plan.daily_chat_limit
            allowed = (limit == -1) or (current < limit)
        elif usage_type == "monthly_chats":
            current = usage.monthly_chats_used
            limit = plan.monthly_chat_limit
            allowed = (limit == -1) or (current < limit)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid usage type: {usage_type}"
            )

        logger = get_logger('billing-service')
        logger.info(f"Checking usage limit: {usage_type}, current: {current}, limit: {limit}, allowed: {allowed}")

        return LimitCheckResponse(
            allowed=allowed,
            usage_type=usage_type,
            current_usage=current,
            limit=limit,
            remaining=max(0, limit - current) if limit > 0 else -1,
            unlimited=limit == -1,
            reason=None if allowed else f"{usage_type.replace('_', ' ').title()} limit exceeded"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check usage limit: {str(e)}"
        )
```

### 3.2 Update Service Error Handling

**Chat Service** - `app/services/usage_cache.py`

Add handling for new restriction reasons:

```python
# After limit check call
if not response.get("allowed"):
    reason = response.get("reason", "")

    if reason == "trial_expired":
        raise Exception("Your 14-day trial has expired. Please upgrade to continue chatting.")
    elif reason == "subscription_expired":
        raise Exception("Your subscription has expired. Please renew to continue chatting.")
    elif reason == "payment_required":
        raise Exception("Payment is required to access this feature.")
    else:
        raise Exception(f"Usage limit reached: {reason}")
```

**Onboarding Service** - `app/api/documents.py` and `app/api/website_ingestions.py`

```python
# After limit check
if not limit_check["allowed"]:
    reason = limit_check.get("reason", "")

    if reason == "trial_expired":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your 14-day trial has expired. Please upgrade to continue uploading documents."
        )
    elif reason == "subscription_expired":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your subscription has expired. Please renew to continue."
        )
    elif reason == "payment_required":
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Payment is required to access this feature."
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Usage limit reached: {reason}"
        )
```

---

## Phase 4: Email Notification System

### 4.1 Create Email Service

**File:** `billing-service/app/services/email_service.py`

```python
"""
Email notification service for subscription and payment events
"""
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from typing import Optional
import os

from ..core.database import SessionLocal
from ..models.subscription import Subscription
from ..models.notification import NotificationLog

logger = logging.getLogger(__name__)

# Email configuration from environment
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
SMTP_FROM = os.environ.get("SMTP_FROM", "noreply@factorialbot.com")

def send_email(to_email: str, subject: str, html_content: str, tenant_id: str,
               subscription_id: str, notification_type: str) -> bool:
    """Send email and log notification"""
    try:
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = SMTP_FROM
        msg['To'] = to_email

        # Attach HTML content
        html_part = MIMEText(html_content, 'html')
        msg.attach(html_part)

        # Send email
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)

        # Log notification
        db = SessionLocal()
        try:
            log = NotificationLog(
                tenant_id=tenant_id,
                subscription_id=subscription_id,
                notification_type=notification_type,
                email_to=to_email,
                subject=subject,
                status="sent",
                sent_at=datetime.now(timezone.utc)
            )
            db.add(log)
            db.commit()
        finally:
            db.close()

        logger.info(f"✅ Email sent: {notification_type} to {to_email}")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to send email: {e}", exc_info=True)

        # Log failure
        db = SessionLocal()
        try:
            log = NotificationLog(
                tenant_id=tenant_id,
                subscription_id=subscription_id,
                notification_type=notification_type,
                email_to=to_email,
                subject=subject,
                status="failed",
                error_message=str(e),
                sent_at=datetime.now(timezone.utc)
            )
            db.add(log)
            db.commit()
        finally:
            db.close()

        return False

def get_tenant_email(tenant_id: str) -> Optional[str]:
    """Get tenant email from authorization server or database"""
    # TODO: Implement tenant email lookup
    # For now, return placeholder
    return f"tenant-{tenant_id}@example.com"

def send_trial_expiring_email(tenant_id: str, subscription_id: str):
    """Send email 3 days before trial ends"""
    email = get_tenant_email(tenant_id)
    if not email:
        return

    subject = "Your FactorialBot Trial Expires in 3 Days"
    html_content = f"""
    <html>
    <body>
        <h2>Your Trial is Expiring Soon</h2>
        <p>Your 14-day trial of FactorialBot will expire in <strong>3 days</strong>.</p>
        <p>To continue using FactorialBot without interruption, please upgrade your plan:</p>
        <p><a href="https://factorialbot.com/billing/upgrade">Upgrade Now</a></p>
        <p>After your trial expires, you will lose access to:</p>
        <ul>
            <li>Chat functionality</li>
            <li>Document uploads</li>
            <li>Website ingestion</li>
        </ul>
        <p>Questions? Contact us at support@factorialbot.com</p>
    </body>
    </html>
    """

    send_email(email, subject, html_content, tenant_id, subscription_id, "trial_expiring_soon")

def send_trial_expired_email(tenant_id: str, subscription_id: str):
    """Send email when trial has expired"""
    email = get_tenant_email(tenant_id)
    if not email:
        return

    subject = "Your FactorialBot Trial Has Expired"
    html_content = f"""
    <html>
    <body>
        <h2>Your Trial Has Expired</h2>
        <p>Your 14-day trial of FactorialBot has ended.</p>
        <p>Your account is now restricted. To regain access, please upgrade to a paid plan:</p>
        <p><a href="https://factorialbot.com/billing/upgrade">Upgrade Now</a></p>
        <p><strong>What's restricted:</strong></p>
        <ul>
            <li>❌ Chat messages</li>
            <li>❌ Document uploads</li>
            <li>❌ Website ingestion</li>
        </ul>
        <p>We hope you enjoyed your trial! Upgrade today to continue using FactorialBot.</p>
    </body>
    </html>
    """

    send_email(email, subject, html_content, tenant_id, subscription_id, "trial_expired")

def send_subscription_expiring_email(tenant_id: str, subscription_id: str):
    """Send email 7 days before subscription expires"""
    email = get_tenant_email(tenant_id)
    if not email:
        return

    subject = "Your FactorialBot Subscription Expires in 7 Days"
    html_content = f"""
    <html>
    <body>
        <h2>Time to Renew Your Subscription</h2>
        <p>Your FactorialBot subscription will expire in <strong>7 days</strong>.</p>
        <p>To avoid service interruption, please renew your subscription:</p>
        <p><a href="https://factorialbot.com/billing/renew">Renew Now</a></p>
        <p>After expiration, your account will be restricted until payment is received.</p>
        <p>Thank you for being a valued customer!</p>
    </body>
    </html>
    """

    send_email(email, subject, html_content, tenant_id, subscription_id, "subscription_expiring_soon")

def send_subscription_expired_email(tenant_id: str, subscription_id: str):
    """Send email when subscription has expired"""
    email = get_tenant_email(tenant_id)
    if not email:
        return

    subject = "Your FactorialBot Subscription Has Expired"
    html_content = f"""
    <html>
    <body>
        <h2>Your Subscription Has Expired</h2>
        <p>Your FactorialBot subscription has expired.</p>
        <p>Your account is now restricted. To regain access, please renew your subscription:</p>
        <p><a href="https://factorialbot.com/billing/renew">Renew Now</a></p>
        <p><strong>What's restricted:</strong></p>
        <ul>
            <li>❌ Chat messages</li>
            <li>❌ Document uploads</li>
            <li>❌ Website ingestion</li>
        </ul>
        <p>We'd love to have you back! Renew today.</p>
    </body>
    </html>
    """

    send_email(email, subject, html_content, tenant_id, subscription_id, "subscription_expired")

def send_payment_successful_email(tenant_id: str, subscription_id: str, amount: float):
    """Send email after successful payment"""
    email = get_tenant_email(tenant_id)
    if not email:
        return

    subject = "Payment Received - FactorialBot"
    html_content = f"""
    <html>
    <body>
        <h2>Payment Successful!</h2>
        <p>We've received your payment of <strong>NGN {amount:,.2f}</strong>.</p>
        <p>Your FactorialBot subscription is now active.</p>
        <p>Thank you for your payment!</p>
        <p><a href="https://factorialbot.com/dashboard">Go to Dashboard</a></p>
    </body>
    </html>
    """

    send_email(email, subject, html_content, tenant_id, subscription_id, "payment_successful")

def send_subscription_renewed_email(tenant_id: str, subscription_id: str):
    """Send email after subscription renewal"""
    email = get_tenant_email(tenant_id)
    if not email:
        return

    subject = "Subscription Renewed - FactorialBot"
    html_content = f"""
    <html>
    <body>
        <h2>Subscription Renewed!</h2>
        <p>Your FactorialBot subscription has been successfully renewed.</p>
        <p>Your account is now active for another month.</p>
        <p><a href="https://factorialbot.com/dashboard">Go to Dashboard</a></p>
    </body>
    </html>
    """

    send_email(email, subject, html_content, tenant_id, subscription_id, "subscription_renewed")
```

### 4.2 Create Notification Model

**File:** `billing-service/app/models/notification.py`

```python
"""
Notification tracking model
"""
import uuid
from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.sql import func
from ..core.database import Base

class NotificationLog(Base):
    """Track sent email notifications"""
    __tablename__ = "notification_logs"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), nullable=False, index=True)
    subscription_id = Column(String(36), nullable=False, index=True)
    notification_type = Column(String(50), nullable=False, index=True)
    email_to = Column(String(255), nullable=False)
    subject = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False)  # sent, failed
    error_message = Column(Text, nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

### 4.3 Environment Variables for Email

Add to `.env` files:

```bash
# Email Configuration
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM=noreply@factorialbot.com
```

---

## Phase 5: Payment & Renewal Workflow Enhancements

### 5.1 Add Renewal Endpoint

**File:** `billing-service/app/api/subscriptions.py`

```python
@router.post("/renew", response_model=Dict[str, Any])
async def renew_subscription(
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Renew an expired or expiring subscription.
    Returns Paystack payment authorization URL.
    """

    try:
        subscription_service = SubscriptionService(db)

        # Get subscription
        subscription = subscription_service.get_subscription_by_tenant(claims.tenant_id)
        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No subscription found"
            )

        # Only EXPIRED or ACTIVE (near expiration) can be renewed
        if subscription.status not in [SubscriptionStatus.EXPIRED, SubscriptionStatus.ACTIVE]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot renew subscription with status: {subscription.status}"
            )

        # Initialize payment for renewal
        result = await subscription_service.initialize_subscription_payment(
            subscription_id=subscription.id,
            tenant_email=claims.email,  # Assumes email is in JWT claims
            metadata={
                "renewal": True,
                "previous_status": subscription.status
            }
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate renewal: {str(e)}"
        )

@router.get("/renewal-required", response_model=Dict[str, Any])
async def check_renewal_required(
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Check if subscription needs renewal.
    Used for UI banners/prompts.
    """

    try:
        subscription_service = SubscriptionService(db)
        subscription = subscription_service.get_subscription_by_tenant(claims.tenant_id)

        if not subscription:
            return {
                "renewal_required": True,
                "reason": "no_subscription",
                "message": "No subscription found"
            }

        now = datetime.now(timezone.utc)

        # EXPIRED - needs renewal immediately
        if subscription.status == SubscriptionStatus.EXPIRED:
            return {
                "renewal_required": True,
                "reason": "expired",
                "message": "Your subscription has expired",
                "expired_at": subscription.ends_at.isoformat() if subscription.ends_at else None
            }

        # TRIALING - check if trial is expiring soon
        if subscription.status == SubscriptionStatus.TRIALING:
            if subscription.trial_ends_at:
                days_remaining = (subscription.trial_ends_at - now).days
                if days_remaining <= 3:
                    return {
                        "renewal_required": True,
                        "reason": "trial_expiring",
                        "message": f"Your trial expires in {days_remaining} days",
                        "days_remaining": days_remaining,
                        "expires_at": subscription.trial_ends_at.isoformat()
                    }

        # ACTIVE - check if expiring soon
        if subscription.status == SubscriptionStatus.ACTIVE:
            if subscription.ends_at:
                days_remaining = (subscription.ends_at - now).days
                if days_remaining <= 7:
                    return {
                        "renewal_required": True,
                        "reason": "expiring_soon",
                        "message": f"Your subscription expires in {days_remaining} days",
                        "days_remaining": days_remaining,
                        "expires_at": subscription.ends_at.isoformat()
                    }

        return {
            "renewal_required": False,
            "reason": None,
            "message": "Subscription is active"
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check renewal status: {str(e)}"
        )
```

### 5.2 Update Payment Verification to Handle Renewals

**File:** `billing-service/app/services/subscription_service.py`

**Modify `verify_subscription_payment()` method:**

```python
async def verify_subscription_payment(
    self,
    payment_reference: str
) -> Dict[str, Any]:
    """Verify payment and activate/renew subscription"""

    # ... existing verification code ...

    # After payment verification succeeds:
    subscription = self.get_subscription_by_id(payment.subscription_id)
    if subscription:
        now = datetime.utcnow()

        # Check if this is a renewal (subscription was EXPIRED)
        is_renewal = subscription.status == SubscriptionStatus.EXPIRED

        # Activate subscription
        subscription.status = SubscriptionStatus.ACTIVE

        # Update subscription dates for renewal
        if is_renewal:
            # Reset to new 30-day period
            subscription.starts_at = now
            subscription.ends_at = now + timedelta(days=30)
            subscription.current_period_start = now
            subscription.current_period_end = now + timedelta(days=30)

            # Clear trial dates (no longer relevant)
            subscription.trial_starts_at = None
            subscription.trial_ends_at = None

            # Reset usage counters
            usage = self.db.query(UsageTracking).filter(
                UsageTracking.subscription_id == subscription.id
            ).first()

            if usage:
                usage.documents_used = 0
                usage.websites_used = 0
                usage.daily_chats_used = 0
                usage.monthly_chats_used = 0
                usage.daily_reset_at = now + timedelta(days=1)
                usage.monthly_reset_at = now + timedelta(days=30)
                usage.period_start = now
                usage.period_end = now + timedelta(days=30)

        self.db.commit()

        # Send appropriate email
        if is_renewal:
            from ..services.email_service import send_subscription_renewed_email
            send_subscription_renewed_email(subscription.tenant_id, subscription.id)
        else:
            from ..services.email_service import send_payment_successful_email
            send_payment_successful_email(
                subscription.tenant_id,
                subscription.id,
                float(payment.amount)
            )

    return {
        "success": True,
        "message": "Payment verified successfully",
        "subscription_activated": True,
        "is_renewal": is_renewal
    }
```

---

## Phase 6: Webhook Enhancements

### 6.1 Update Paystack Webhook Handler

**File:** `billing-service/app/api/webhooks.py`

**Enhance webhook handler to properly handle subscription lifecycle:**

```python
@router.post("/paystack")
async def handle_paystack_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """Handle Paystack webhook events"""

    try:
        # Get raw body for signature verification
        body = await request.body()
        signature = request.headers.get("x-paystack-signature")

        # Verify signature
        paystack_service = PaystackService(db)
        if not paystack_service.verify_webhook_signature(body, signature):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid webhook signature"
            )

        # Parse event
        event = await request.json()
        event_type = event.get("event")
        data = event.get("data", {})

        logger.info(f"Received Paystack webhook: {event_type}")

        # Log webhook
        webhook_log = PaystackWebhook(
            event_type=event_type,
            event_data=event,
            signature=signature,
            processed=False
        )
        db.add(webhook_log)
        db.commit()

        # Handle different event types
        if event_type == "charge.success":
            reference = data.get("reference")
            if reference:
                # Find payment
                payment = db.query(Payment).filter(
                    Payment.paystack_reference == reference
                ).first()

                if payment and payment.subscription_id:
                    subscription_service = SubscriptionService(db)

                    # Verify and activate subscription
                    await subscription_service.verify_subscription_payment(reference)

                    webhook_log.processed = True
                    db.commit()

        elif event_type == "subscription.disable":
            # Handle subscription cancellation (if auto-renew added later)
            customer_code = data.get("customer", {}).get("customer_code")
            # Mark subscription as cancelled
            pass

        elif event_type == "invoice.payment_failed":
            # Handle failed payment
            reference = data.get("reference")
            if reference:
                payment = db.query(Payment).filter(
                    Payment.paystack_reference == reference
                ).first()

                if payment and payment.subscription_id:
                    # Mark subscription as PAST_DUE
                    subscription = db.query(Subscription).filter(
                        Subscription.id == payment.subscription_id
                    ).first()

                    if subscription:
                        subscription.status = SubscriptionStatus.PAST_DUE
                        db.commit()

                    webhook_log.processed = True
                    db.commit()

        return {"status": "success"}

    except Exception as e:
        logger.error(f"Webhook processing error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
```

---

## Phase 7: Testing Strategy

### 7.1 Manual Testing Checklist

**Trial Expiration:**
1. Create subscription with `trial_ends_at` in the past
2. Attempt to upload document → should be blocked
3. Attempt to chat → should be blocked
4. Check subscription status via API → should show EXPIRED

**Subscription Expiration:**
1. Create ACTIVE subscription with `ends_at` in the past
2. Attempt actions → should be blocked
3. Renew subscription via payment
4. Verify usage counters reset to 0

**Email Notifications:**
1. Use mailtrap.io or similar for testing
2. Manually trigger scheduled jobs
3. Verify emails are sent and logged

**Payment Flow:**
1. Initialize payment for renewal
2. Complete payment on Paystack (use test card)
3. Verify webhook received
4. Verify subscription status updated to ACTIVE
5. Verify usage counters reset

### 7.2 Automated Tests

Create test files:
- `tests/test_trial_expiration.py`
- `tests/test_subscription_renewal.py`
- `tests/test_scheduled_jobs.py`
- `tests/test_email_notifications.py`

---

## Phase 8: Production Deployment

### 8.1 Pre-Deployment Checklist

- [ ] Run database migration (add EXPIRED status, notification_logs table)
- [ ] Update environment variables (SMTP settings, Paystack keys)
- [ ] Test scheduled jobs manually
- [ ] Test email delivery
- [ ] Test payment flow end-to-end
- [ ] Backfill existing subscriptions (set correct statuses)

### 8.2 Deployment Steps

1. Stop billing service
2. Run Alembic migrations
3. Deploy new code
4. Start billing service (scheduler will auto-start)
5. Monitor logs for scheduler startup
6. Monitor webhook deliveries
7. Monitor email delivery

### 8.3 Rollback Plan

If issues occur:
1. Stop billing service
2. Revert to previous version
3. Scheduler will stop automatically
4. No data loss (migrations are additive)

---

## Environment Variables Required

Add to `billing-service/.env`:

```bash
# Email Configuration
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=noreply@factorialbot.com
SMTP_PASSWORD=your-app-specific-password
SMTP_FROM=FactorialBot <noreply@factorialbot.com>

# Paystack Configuration (you already have these)
PAYSTACK_SECRET_KEY=sk_live_your_secret_key
PAYSTACK_PUBLIC_KEY=pk_live_your_public_key
PAYSTACK_WEBHOOK_SECRET=whsec_your_webhook_secret

# Scheduler Configuration
SCHEDULER_TIMEZONE=Africa/Lagos
```

---

## Monitoring & Alerts

### Key Metrics to Monitor

1. **Scheduled Jobs**
   - Job execution count
   - Job failure rate
   - Expiration check results

2. **Email Delivery**
   - Sent vs failed ratio
   - Notification types sent
   - Bounce rate

3. **Payment Processing**
   - Successful payments
   - Failed payments
   - Webhook processing time

4. **Subscription Health**
   - Active vs expired subscriptions
   - Trial conversion rate
   - Renewal rate

---

## Summary

This implementation provides:

✅ **Complete Trial Management**
- 14-day trial on registration
- Automatic expiration checks
- Email reminders (3 days before)
- Immediate restriction on expiration

✅ **Subscription Lifecycle**
- TRIALING → ACTIVE (on payment) → EXPIRED (on end)
- Manual renewal workflow
- Usage counter resets on renewal
- Period date updates

✅ **Account Restrictions**
- Chat blocked for expired subscriptions
- Document/website uploads blocked
- Clear error messages

✅ **Email Notifications**
- Trial expiring (3 days before)
- Trial expired (on expiration)
- Subscription expiring (7 days before)
- Subscription expired (on expiration)
- Payment successful
- Subscription renewed

✅ **Industry Best Practices**
- Proration on upgrades (already implemented)
- Scheduled downgrades (already implemented)
- Manual renewal (no auto-charge)
- Webhook security
- Idempotent processing
- Audit trails

✅ **Background Jobs**
- APScheduler for scheduled tasks
- Hourly trial expiration checks
- Daily subscription expiration checks
- Daily email reminders
- Automatic status updates

---

## Next Steps

When ready to implement, execute in this order:

1. **Phase 1** - Database updates (migrations)
2. **Phase 3** - Account restrictions (CRITICAL - blocks expired users)
3. **Phase 5** - Renewal workflow (enables users to pay)
4. **Phase 2** - Background jobs (automates expiration)
5. **Phase 4** - Email notifications (user communication)
6. **Phase 6** - Webhook enhancements (payment processing)
7. **Phase 7** - Testing (quality assurance)
8. **Phase 8** - Production deployment

This ensures critical functionality (restrictions + renewal) is implemented first, then automation is layered on top.