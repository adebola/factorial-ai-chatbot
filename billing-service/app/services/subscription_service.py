from decimal import Decimal
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import uuid

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from ..core.config import settings
from ..models.plan import Plan
from ..models.subscription import (
    Subscription, SubscriptionStatus, BillingCycle, Payment, PaymentStatus,
    PaymentMethod, TransactionType, SubscriptionChange, UsageTracking,
    PaymentMethodRecord, Invoice
)
from .paystack_service import PaystackService
from .plan_service import PlanService


class SubscriptionService:
    """Service for managing subscriptions and billing"""

    def __init__(self, db: Session):
        self.db = db
        self.paystack = PaystackService(db)
        self.plan_service = PlanService(db)

    def create_subscription(
        self,
        tenant_id: str,
        plan_id: str,
        billing_cycle: BillingCycle = BillingCycle.MONTHLY,
        start_trial: bool = False,
        custom_trial_end: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Subscription:
        """Create a new subscription for a tenant

        Args:
            tenant_id: UUID of the tenant
            plan_id: UUID of the plan
            billing_cycle: Monthly or yearly billing
            start_trial: Whether to start a trial period
            custom_trial_end: Custom trial end date (overrides default trial period)
            metadata: Additional metadata
        """

        # Validate tenant_id format (tenant data is in OAuth2 server)
        if not tenant_id or len(tenant_id) != 36:
            raise ValueError("Invalid tenant_id format")

        plan = self.plan_service.get_plan_by_id(plan_id)
        if not plan or not plan.is_active:
            raise ValueError("Plan not found or inactive")

        # Calculate subscription amount based on billing cycle
        if billing_cycle == BillingCycle.YEARLY:
            amount = plan.yearly_plan_cost
        else:
            amount = plan.monthly_plan_cost

        # Calculate dates
        now = datetime.utcnow()

        if custom_trial_end:
            # Use custom trial end date (e.g., 14 days from registration)
            trial_starts_at = now
            trial_ends_at = custom_trial_end
            starts_at = trial_ends_at
            status = SubscriptionStatus.TRIALING
        elif start_trial and settings.TRIAL_PERIOD_DAYS > 0:
            # Standard trial period
            trial_starts_at = now
            trial_ends_at = now + timedelta(days=settings.TRIAL_PERIOD_DAYS)
            starts_at = trial_ends_at
            status = SubscriptionStatus.TRIALING
        else:
            # No trial
            trial_starts_at = None
            trial_ends_at = None
            starts_at = now
            status = SubscriptionStatus.PENDING

        # Calculate subscription end date
        if billing_cycle == BillingCycle.YEARLY:
            ends_at = starts_at + timedelta(days=365)
            current_period_end = starts_at + timedelta(days=365)
        else:
            ends_at = starts_at + timedelta(days=30)
            current_period_end = starts_at + timedelta(days=30)

        # Create subscription
        subscription = Subscription(
            tenant_id=tenant_id,
            plan_id=plan_id,
            status=status,
            billing_cycle=billing_cycle,
            amount=amount,
            currency=settings.DEFAULT_CURRENCY,
            starts_at=starts_at,
            ends_at=ends_at,
            current_period_start=starts_at,
            current_period_end=current_period_end,
            trial_starts_at=trial_starts_at,
            trial_ends_at=trial_ends_at,
            subscription_metadata=metadata or {}
        )

        self.db.add(subscription)
        self.db.commit()
        self.db.refresh(subscription)

        # Initialize usage tracking
        self._initialize_usage_tracking(subscription)

        # Log subscription creation
        self._log_subscription_change(
            subscription=subscription,
            change_type="created",
            new_plan_id=plan_id,
            new_amount=amount,
            reason="Initial subscription creation"
        )

        return subscription

    async def initialize_subscription_payment(
        self,
        subscription_id: str,
        tenant_email: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Initialize payment for a subscription"""

        subscription = self.get_subscription_by_id(subscription_id)
        if not subscription:
            raise ValueError("Subscription not found")

        if subscription.status != SubscriptionStatus.PENDING:
            raise ValueError("Subscription is not pending payment")

        # Generate payment reference
        reference = f"sub_{subscription.id}_{uuid.uuid4().hex[:8]}"

        # Prepare payment metadata
        payment_metadata = {
            "subscription_id": subscription.id,
            "tenant_id": subscription.tenant_id,
            "plan_id": subscription.plan_id,
            "billing_cycle": subscription.billing_cycle,
            "transaction_type": TransactionType.SUBSCRIPTION.value,
            **(metadata or {})
        }

        # Initialize payment with Paystack
        result = await self.paystack.initialize_transaction(
            email=tenant_email,
            amount=subscription.amount,
            currency=subscription.currency,
            reference=reference,
            metadata=payment_metadata
        )

        if result["success"]:
            # Create payment record
            payment = Payment(
                subscription_id=subscription.id,
                tenant_id=subscription.tenant_id,
                amount=subscription.amount,
                currency=subscription.currency,
                status=PaymentStatus.PENDING,
                transaction_type=TransactionType.SUBSCRIPTION,
                paystack_reference=reference,
                paystack_access_code=result["access_code"],
                description=f"Subscription payment for {subscription.billing_cycle} plan",
                payment_metadata=payment_metadata
            )

            self.db.add(payment)
            self.db.commit()
            self.db.refresh(payment)

            return {
                "success": True,
                "payment_id": payment.id,
                "reference": reference,
                "access_code": result["access_code"],
                "authorization_url": result["authorization_url"],
                "amount": float(subscription.amount)
            }
        else:
            return {
                "success": False,
                "error": result["error"]
            }

    async def verify_subscription_payment(
        self,
        reference: str,
        expected_amount: Optional[Decimal] = None
    ) -> Dict[str, Any]:
        """Verify and process subscription payment"""

        # Get payment record
        payment = self.db.query(Payment).filter(
            Payment.paystack_reference == reference
        ).first()

        if not payment:
            return {"success": False, "error": "Payment record not found"}

        # Verify with Paystack
        verification_result = await self.paystack.verify_transaction(reference)

        if not verification_result["success"]:
            return {"success": False, "error": verification_result["error"]}

        if not verification_result["verified"]:
            payment.status = PaymentStatus.FAILED
            payment.failure_reason = "Payment not verified by Paystack"
            self.db.commit()
            return {"success": False, "error": "Payment verification failed"}

        # Verify amount
        paid_amount = verification_result["amount"]
        if expected_amount and abs(paid_amount - expected_amount) > Decimal("0.01"):
            payment.status = PaymentStatus.FAILED
            payment.failure_reason = f"Amount mismatch: expected {expected_amount}, got {paid_amount}"
            self.db.commit()
            return {"success": False, "error": "Payment amount mismatch"}

        # Update payment record
        payment.status = PaymentStatus.COMPLETED
        payment.processed_at = datetime.utcnow()
        payment.gateway_response = verification_result["data"]
        payment.paystack_transaction_id = str(verification_result["transaction_id"])

        # Store payment method if available
        auth_data = verification_result.get("authorization", {})
        if auth_data.get("authorization_code"):
            self._store_payment_method(payment.tenant_id, auth_data, verification_result.get("customer", {}))

        # Activate subscription
        subscription = self.get_subscription_by_id(payment.subscription_id)
        if subscription:
            subscription.status = SubscriptionStatus.ACTIVE

            # NOTE: Tenant plan updates handled by OAuth2 server
            # tenant.plan_id would be updated via OAuth2 server API call

        self.db.commit()

        return {
            "success": True,
            "payment_id": payment.id,
            "subscription_id": payment.subscription_id,
            "amount": float(paid_amount),
            "transaction_id": payment.paystack_transaction_id
        }

    def switch_subscription_plan(
        self,
        subscription_id: str,
        new_plan_id: str,
        billing_cycle: Optional[BillingCycle] = None,
        prorate: bool = True
    ) -> Dict[str, Any]:
        """Switch subscription to a different plan"""

        subscription = self.get_subscription_by_id(subscription_id)
        if not subscription:
            raise ValueError("Subscription not found")

        if subscription.status not in [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]:
            raise ValueError("Can only switch active or trialing subscriptions")

        # Get new plan
        new_plan = self.plan_service.get_plan_by_id(new_plan_id)
        if not new_plan or not new_plan.is_active:
            raise ValueError("New plan not found or inactive")

        # Get current plan for comparison
        current_plan = self.plan_service.get_plan_by_id(subscription.plan_id)

        # Use current billing cycle if not specified
        if not billing_cycle:
            billing_cycle = subscription.billing_cycle

        # Calculate new amount
        if billing_cycle == BillingCycle.YEARLY:
            new_amount = new_plan.yearly_plan_cost
            old_amount = current_plan.yearly_plan_cost if current_plan else Decimal(0)
        else:
            new_amount = new_plan.monthly_plan_cost
            old_amount = current_plan.monthly_plan_cost if current_plan else Decimal(0)

        # Calculate prorated amount if needed (for both ACTIVE and TRIALING subscriptions)
        prorated_amount = None
        if prorate and subscription.status in [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]:
            prorated_amount = self._calculate_proration(
                subscription, old_amount, new_amount, billing_cycle
            )

        # Determine if this is a downgrade (lower cost plan)
        is_downgrade = new_amount < old_amount

        # Handle downgrades: Schedule for end-of-period (industry standard)
        if is_downgrade and subscription.status == SubscriptionStatus.ACTIVE:
            # Schedule downgrade for end of current period
            subscription.pending_plan_id = new_plan_id
            subscription.pending_billing_cycle = billing_cycle
            subscription.pending_plan_effective_date = subscription.current_period_end

            # Log the scheduled change
            self._log_subscription_change(
                subscription=subscription,
                change_type="downgrade_scheduled",
                previous_plan_id=subscription.plan_id,
                new_plan_id=new_plan_id,
                previous_amount=old_amount,
                new_amount=new_amount,
                reason=f"Downgrade scheduled for end of period ({subscription.current_period_end.isoformat()})"
            )

            self.db.commit()

            return {
                "success": True,
                "subscription_id": subscription.id,
                "old_plan_id": subscription.plan_id,
                "new_plan_id": new_plan_id,
                "old_amount": float(old_amount),
                "new_amount": float(new_amount),
                "prorated_amount": None,  # No charge for scheduled downgrade
                "effective_immediately": False,
                "scheduled_for": subscription.current_period_end.isoformat(),
                "message": f"Your plan will be downgraded to {new_plan.name} at the end of your current billing period ({subscription.current_period_end.date()}). You'll continue to enjoy {current_plan.name if current_plan else 'your current plan'} features until then."
            }

        # Handle upgrades and immediate changes: Apply immediately
        old_plan_id = subscription.plan_id
        subscription.plan_id = new_plan_id
        subscription.amount = new_amount
        subscription.billing_cycle = billing_cycle

        # If upgrading from TRIALING status, change to ACTIVE (user is now paying)
        was_trialing = subscription.status == SubscriptionStatus.TRIALING
        if was_trialing and new_amount > old_amount:
            subscription.status = SubscriptionStatus.ACTIVE
            subscription.trial_ends_at = None  # End trial immediately
            subscription.starts_at = datetime.utcnow()  # Update start date to now

        # Clear any pending plan changes (user upgraded before scheduled downgrade)
        if subscription.pending_plan_id:
            subscription.pending_plan_id = None
            subscription.pending_billing_cycle = None
            subscription.pending_plan_effective_date = None

        # NOTE: Tenant plan updates handled by OAuth2 server
        # tenant.plan_id would be updated via OAuth2 server API call

        # Log the change
        change_type = "upgrade" if new_amount > old_amount else "plan_change"
        self._log_subscription_change(
            subscription=subscription,
            change_type=change_type,
            previous_plan_id=old_plan_id,
            new_plan_id=new_plan_id,
            previous_amount=old_amount,
            new_amount=new_amount,
            prorated_amount=prorated_amount,
            reason="User initiated plan change"
        )

        self.db.commit()

        return {
            "success": True,
            "subscription_id": subscription.id,
            "old_plan_id": old_plan_id,
            "new_plan_id": new_plan_id,
            "old_amount": float(old_amount),
            "new_amount": float(new_amount),
            "prorated_amount": float(prorated_amount) if prorated_amount else None,
            "effective_immediately": True
        }

    def cancel_subscription(
        self,
        subscription_id: str,
        cancel_at_period_end: bool = True,
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """Cancel a subscription"""

        subscription = self.get_subscription_by_id(subscription_id)
        if not subscription:
            raise ValueError("Subscription not found")

        if subscription.status == SubscriptionStatus.CANCELLED:
            return {"success": False, "error": "Subscription already cancelled"}

        now = datetime.utcnow()

        if cancel_at_period_end:
            # Cancel at end of current period
            subscription.cancel_at_period_end = True
            subscription.cancellation_reason = reason
            status = subscription.status  # Keep current status until period ends
        else:
            # Cancel immediately
            subscription.status = SubscriptionStatus.CANCELLED
            subscription.cancelled_at = now
            subscription.cancellation_reason = reason
            status = SubscriptionStatus.CANCELLED

        # Log cancellation
        self._log_subscription_change(
            subscription=subscription,
            change_type="cancelled",
            reason=reason or "User requested cancellation"
        )

        self.db.commit()

        return {
            "success": True,
            "subscription_id": subscription.id,
            "cancelled_immediately": not cancel_at_period_end,
            "cancellation_effective_date": subscription.current_period_end.isoformat() if cancel_at_period_end else now.isoformat(),
            "status": status.value
        }

    def get_subscription_by_id(self, subscription_id: str) -> Optional[Subscription]:
        """Get subscription by ID"""
        return self.db.query(Subscription).filter(Subscription.id == subscription_id).first()

    def get_subscription_by_tenant(self, tenant_id: str) -> Optional[Subscription]:
        """Get active subscription for a tenant"""
        return self.db.query(Subscription).filter(
            and_(
                Subscription.tenant_id == tenant_id,
                Subscription.status.in_(['active', 'trialing', 'past_due'])
            )
        ).first()

    def get_tenant_subscription_history(self, tenant_id: str) -> List[Subscription]:
        """Get all subscriptions for a tenant"""
        return self.db.query(Subscription).filter(
            Subscription.tenant_id == tenant_id
        ).order_by(Subscription.created_at.desc()).all()

    def _initialize_usage_tracking(self, subscription: Subscription) -> None:
        """Initialize usage tracking for a new subscription"""
        now = datetime.utcnow()
        usage_tracking = UsageTracking(
            tenant_id=subscription.tenant_id,
            subscription_id=subscription.id,
            period_start=subscription.current_period_start,
            period_end=subscription.current_period_end,
            daily_reset_at=now + timedelta(days=1),
            monthly_reset_at=now + timedelta(days=30)
        )

        self.db.add(usage_tracking)
        self.db.commit()

    def check_and_reset_usage_periods(self, usage: UsageTracking) -> UsageTracking:
        """Check if usage periods need to be reset and apply resets if needed"""
        from datetime import timezone as tz
        now = datetime.now(tz.utc)
        needs_commit = False

        # Check and reset daily usage
        if usage.daily_reset_at and now >= usage.daily_reset_at:
            usage.daily_chats_used = 0
            usage.daily_reset_at = now + timedelta(days=1)
            needs_commit = True
        elif not usage.daily_reset_at:
            # Initialize if not set
            usage.daily_reset_at = now + timedelta(days=1)
            needs_commit = True

        # Check and reset monthly usage
        if usage.monthly_reset_at and now >= usage.monthly_reset_at:
            usage.monthly_chats_used = 0
            usage.monthly_reset_at = now + timedelta(days=30)
            needs_commit = True
        elif not usage.monthly_reset_at:
            # Initialize if not set
            usage.monthly_reset_at = now + timedelta(days=30)
            needs_commit = True

        if needs_commit:
            usage.updated_at = now
            self.db.commit()
            self.db.refresh(usage)

        return usage

    def _log_subscription_change(
        self,
        subscription: Subscription,
        change_type: str,
        previous_plan_id: Optional[str] = None,
        new_plan_id: Optional[str] = None,
        previous_amount: Optional[Decimal] = None,
        new_amount: Optional[Decimal] = None,
        prorated_amount: Optional[Decimal] = None,
        reason: Optional[str] = None
    ) -> None:
        """Log a subscription change for audit trail"""

        change = SubscriptionChange(
            subscription_id=subscription.id,
            tenant_id=subscription.tenant_id,
            change_type=change_type,
            previous_plan_id=previous_plan_id,
            new_plan_id=new_plan_id,
            previous_amount=previous_amount,
            new_amount=new_amount,
            prorated_amount=prorated_amount,
            reason=reason,
            effective_at=datetime.utcnow()
        )

        self.db.add(change)

    def _calculate_proration(
        self,
        subscription: Subscription,
        old_amount: Decimal,
        new_amount: Decimal,
        billing_cycle: BillingCycle
    ) -> Decimal:
        """Calculate prorated amount for plan changes"""

        now = datetime.utcnow()
        period_start = subscription.current_period_start
        period_end = subscription.current_period_end

        # Calculate remaining days in current period
        total_days = (period_end - period_start).days
        remaining_days = (period_end - now).days

        if remaining_days <= 0:
            return Decimal(0)

        # Calculate daily rates
        old_daily_rate = old_amount / total_days
        new_daily_rate = new_amount / total_days

        # Calculate unused amount from old plan
        unused_amount = old_daily_rate * remaining_days

        # Calculate amount needed for new plan
        new_amount_needed = new_daily_rate * remaining_days

        # Prorated amount (positive = charge more, negative = credit)
        return new_amount_needed - unused_amount

    def _store_payment_method(
        self,
        tenant_id: str,
        auth_data: Dict[str, Any],
        customer_data: Dict[str, Any]
    ) -> None:
        """Store payment method information"""

        # Check if payment method already exists
        existing = self.db.query(PaymentMethodRecord).filter(
            and_(
                PaymentMethodRecord.tenant_id == tenant_id,
                PaymentMethodRecord.paystack_authorization_code == auth_data.get("authorization_code")
            )
        ).first()

        if existing:
            return  # Already stored

        payment_method = PaymentMethodRecord(
            tenant_id=tenant_id,
            type=PaymentMethod.CARD,  # Assuming card for now
            card_last_four=auth_data.get("last4"),
            card_brand=auth_data.get("brand"),
            card_exp_month=auth_data.get("exp_month"),
            card_exp_year=auth_data.get("exp_year"),
            paystack_authorization_code=auth_data.get("authorization_code"),
            paystack_customer_code=customer_data.get("customer_code"),
            payment_method_metadata={
                "bank": auth_data.get("bank"),
                "country_code": auth_data.get("country_code"),
                "channel": auth_data.get("channel")
            }
        )

        self.db.add(payment_method)
