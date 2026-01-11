"""
Plan Management Service

Handles subscription plan changes including:
- Upgrades (immediate with proration)
- Downgrades (scheduled for end of billing period)
- Plan change previews
- Proration calculations
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
import uuid

from ..models.subscription import Subscription, SubscriptionStatus, BillingCycle
from ..models.plan import Plan
from ..services.email_publisher import email_publisher

logger = logging.getLogger(__name__)


class PlanManagementService:
    """Service for managing plan upgrades, downgrades, and changes"""

    def __init__(self, db: Session):
        self.db = db

    def calculate_proration(
        self,
        subscription: Subscription,
        new_plan: Plan,
        change_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Calculate proration when changing plans mid-cycle.

        For upgrades: User pays the difference for remaining period
        For downgrades: Credit applied to next billing cycle (or scheduled for period end)

        Args:
            subscription: Current subscription
            new_plan: Target plan to change to
            change_date: When the change will take effect (defaults to now)

        Returns:
            Dict with proration details:
                - proration_amount: Amount to charge/credit
                - days_remaining: Days left in current period
                - old_daily_rate: Daily cost of current plan
                - new_daily_rate: Daily cost of new plan
                - is_upgrade: Whether this is an upgrade
        """
        if not change_date:
            change_date = datetime.now(timezone.utc)

        # Get current plan
        current_plan = self.db.query(Plan).filter(Plan.id == subscription.plan_id).first()
        if not current_plan:
            raise ValueError("Current plan not found")

        # Calculate days remaining in current period
        if not subscription.current_period_end:
            raise ValueError("Subscription has no current period end date")

        days_remaining = (subscription.current_period_end - change_date).total_seconds() / 86400
        if days_remaining < 0:
            days_remaining = 0

        # Determine cycle length for daily rate calculation
        if subscription.billing_cycle == BillingCycle.MONTHLY:
            cycle_days = 30
        elif subscription.billing_cycle == BillingCycle.YEARLY:
            cycle_days = 365
        else:
            cycle_days = 30  # Default

        # Calculate daily rates
        old_daily_rate = subscription.amount / Decimal(cycle_days)

        # Get new plan pricing for current billing cycle
        if subscription.billing_cycle == BillingCycle.MONTHLY:
            new_amount = new_plan.monthly_plan_cost
        elif subscription.billing_cycle == BillingCycle.YEARLY:
            new_amount = new_plan.yearly_plan_cost
        else:
            new_amount = new_plan.monthly_plan_cost

        new_daily_rate = new_amount / Decimal(cycle_days)

        # Calculate proration
        remaining_cost_old = old_daily_rate * Decimal(days_remaining)
        remaining_cost_new = new_daily_rate * Decimal(days_remaining)

        proration_amount = remaining_cost_new - remaining_cost_old
        is_upgrade = new_amount > subscription.amount

        logger.info(
            f"Proration calculated: {proration_amount} {subscription.currency}",
            extra={
                "subscription_id": subscription.id,
                "current_plan": current_plan.name,
                "new_plan": new_plan.name,
                "days_remaining": days_remaining,
                "is_upgrade": is_upgrade
            }
        )

        return {
            "proration_amount": float(proration_amount),
            "days_remaining": float(days_remaining),
            "old_daily_rate": float(old_daily_rate),
            "new_daily_rate": float(new_daily_rate),
            "old_amount": float(subscription.amount),
            "new_amount": float(new_amount),
            "is_upgrade": is_upgrade,
            "cycle_days": cycle_days,
            "currency": subscription.currency
        }

    async def upgrade_subscription(
        self,
        subscription_id: str,
        new_plan_id: str,
        user_email: str,
        user_full_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Upgrade subscription to a higher-tier plan.

        Upgrades are applied IMMEDIATELY with proration.
        User is charged the difference for the remaining billing period.

        Args:
            subscription_id: Subscription to upgrade
            new_plan_id: Target plan ID
            user_email: User email for notifications
            user_full_name: User full name for notifications

        Returns:
            Dict with upgrade details and payment information (if needed)
        """
        subscription = self.db.query(Subscription).filter(
            Subscription.id == subscription_id
        ).first()

        if not subscription:
            raise ValueError("Subscription not found")

        if subscription.status not in [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]:
            raise ValueError(f"Cannot upgrade subscription with status: {subscription.status}")

        # Get new plan
        new_plan = self.db.query(Plan).filter(Plan.id == new_plan_id).first()
        if not new_plan:
            raise ValueError("New plan not found")

        # Get current plan for comparison
        current_plan = self.db.query(Plan).filter(Plan.id == subscription.plan_id).first()

        # Determine new amount based on billing cycle
        if subscription.billing_cycle == BillingCycle.MONTHLY:
            new_amount = new_plan.monthly_plan_cost
        elif subscription.billing_cycle == BillingCycle.YEARLY:
            new_amount = new_plan.yearly_plan_cost
        else:
            new_amount = new_plan.monthly_plan_cost

        # Verify this is actually an upgrade
        if new_amount <= subscription.amount:
            raise ValueError("New plan must be higher tier (more expensive) for immediate upgrade")

        # Calculate proration
        proration = self.calculate_proration(subscription, new_plan)

        # Update subscription immediately
        subscription.plan_id = new_plan_id
        subscription.amount = new_amount
        subscription.updated_at = datetime.now(timezone.utc)

        # Store upgrade metadata
        if not subscription.subscription_metadata:
            subscription.subscription_metadata = {}

        subscription.subscription_metadata["last_upgrade"] = {
            "from_plan": current_plan.name,
            "to_plan": new_plan.name,
            "upgraded_at": datetime.now(timezone.utc).isoformat(),
            "proration_charged": proration["proration_amount"]
        }

        self.db.commit()
        self.db.refresh(subscription)

        logger.info(
            f"Subscription upgraded",
            extra={
                "subscription_id": subscription_id,
                "from_plan": current_plan.name,
                "to_plan": new_plan.name,
                "proration": proration["proration_amount"]
            }
        )

        # Send upgrade notification email
        try:
            await email_publisher.publish_plan_upgraded_email(
                tenant_id=subscription.tenant_id,
                to_email=user_email,
                to_name=user_full_name or "User",
                old_plan_name=current_plan.name,
                new_plan_name=new_plan.name,
                proration_amount=proration["proration_amount"],
                currency=subscription.currency
            )
        except Exception as e:
            logger.error(f"Failed to send upgrade notification: {e}", exc_info=True)

        return {
            "success": True,
            "message": f"Subscription upgraded from {current_plan.name} to {new_plan.name}",
            "subscription_id": subscription.id,
            "old_plan": {
                "id": current_plan.id,
                "name": current_plan.name,
                "amount": float(subscription.amount) if subscription.billing_cycle == BillingCycle.MONTHLY else float(subscription.amount)
            },
            "new_plan": {
                "id": new_plan.id,
                "name": new_plan.name,
                "amount": float(new_amount)
            },
            "proration": proration,
            "requires_payment": proration["proration_amount"] > 0,
            "payment_amount": proration["proration_amount"] if proration["proration_amount"] > 0 else 0,
            "effective_date": datetime.now(timezone.utc).isoformat()
        }

    async def downgrade_subscription(
        self,
        subscription_id: str,
        new_plan_id: str,
        user_email: str,
        user_full_name: Optional[str] = None,
        immediate: bool = False
    ) -> Dict[str, Any]:
        """
        Downgrade subscription to a lower-tier plan.

        By default, downgrades are SCHEDULED for end of current billing period.
        User keeps current plan benefits until period ends.

        Args:
            subscription_id: Subscription to downgrade
            new_plan_id: Target plan ID
            user_email: User email for notifications
            user_full_name: User full name for notifications
            immediate: If True, apply downgrade immediately (rare)

        Returns:
            Dict with downgrade details
        """
        subscription = self.db.query(Subscription).filter(
            Subscription.id == subscription_id
        ).first()

        if not subscription:
            raise ValueError("Subscription not found")

        if subscription.status not in [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]:
            raise ValueError(f"Cannot downgrade subscription with status: {subscription.status}")

        # Get new plan
        new_plan = self.db.query(Plan).filter(Plan.id == new_plan_id).first()
        if not new_plan:
            raise ValueError("New plan not found")

        # Get current plan
        current_plan = self.db.query(Plan).filter(Plan.id == subscription.plan_id).first()

        # Determine new amount
        if subscription.billing_cycle == BillingCycle.MONTHLY:
            new_amount = new_plan.monthly_plan_cost
        elif subscription.billing_cycle == BillingCycle.YEARLY:
            new_amount = new_plan.yearly_plan_cost
        else:
            new_amount = new_plan.monthly_plan_cost

        # Verify this is actually a downgrade
        if new_amount >= subscription.amount:
            raise ValueError("New plan must be lower tier (less expensive) for downgrade")

        if immediate:
            # Immediate downgrade (rare case, usually for admin overrides)
            subscription.plan_id = new_plan_id
            subscription.amount = new_amount
            subscription.updated_at = datetime.now(timezone.utc)

            # Clear any pending plan change
            subscription.pending_plan_id = None
            subscription.pending_billing_cycle = None
            subscription.pending_plan_effective_date = None

            effective_date = datetime.now(timezone.utc)
            message = f"Subscription downgraded immediately from {current_plan.name} to {new_plan.name}"
        else:
            # Schedule downgrade for end of billing period
            subscription.pending_plan_id = new_plan_id
            subscription.pending_billing_cycle = subscription.billing_cycle
            subscription.pending_plan_effective_date = subscription.current_period_end
            subscription.updated_at = datetime.now(timezone.utc)

            effective_date = subscription.current_period_end
            message = f"Subscription will downgrade from {current_plan.name} to {new_plan.name} on {effective_date.strftime('%Y-%m-%d')}"

        # Store downgrade metadata
        if not subscription.subscription_metadata:
            subscription.subscription_metadata = {}

        subscription.subscription_metadata["last_downgrade_scheduled"] = {
            "from_plan": current_plan.name,
            "to_plan": new_plan.name,
            "scheduled_at": datetime.now(timezone.utc).isoformat(),
            "effective_date": effective_date.isoformat(),
            "immediate": immediate
        }

        self.db.commit()
        self.db.refresh(subscription)

        logger.info(
            f"Subscription downgrade {'applied' if immediate else 'scheduled'}",
            extra={
                "subscription_id": subscription_id,
                "from_plan": current_plan.name,
                "to_plan": new_plan.name,
                "effective_date": effective_date.isoformat(),
                "immediate": immediate
            }
        )

        # Send downgrade notification email
        try:
            await email_publisher.publish_plan_downgraded_email(
                tenant_id=subscription.tenant_id,
                to_email=user_email,
                to_name=user_full_name or "User",
                old_plan_name=current_plan.name,
                new_plan_name=new_plan.name,
                effective_date=effective_date,
                immediate=immediate
            )
        except Exception as e:
            logger.error(f"Failed to send downgrade notification: {e}", exc_info=True)

        return {
            "success": True,
            "message": message,
            "subscription_id": subscription.id,
            "old_plan": {
                "id": current_plan.id,
                "name": current_plan.name,
                "amount": float(subscription.amount if immediate else subscription.amount)
            },
            "new_plan": {
                "id": new_plan.id,
                "name": new_plan.name,
                "amount": float(new_amount)
            },
            "immediate": immediate,
            "effective_date": effective_date.isoformat(),
            "current_period_end": subscription.current_period_end.isoformat() if subscription.current_period_end else None
        }

    def preview_plan_change(
        self,
        subscription_id: str,
        new_plan_id: str
    ) -> Dict[str, Any]:
        """
        Preview the impact of changing to a different plan.

        Shows proration, new pricing, and effective date without making changes.

        Args:
            subscription_id: Subscription to preview change for
            new_plan_id: Target plan ID

        Returns:
            Dict with preview details
        """
        subscription = self.db.query(Subscription).filter(
            Subscription.id == subscription_id
        ).first()

        if not subscription:
            raise ValueError("Subscription not found")

        new_plan = self.db.query(Plan).filter(Plan.id == new_plan_id).first()
        if not new_plan:
            raise ValueError("New plan not found")

        current_plan = self.db.query(Plan).filter(Plan.id == subscription.plan_id).first()

        # Determine new amount
        if subscription.billing_cycle == BillingCycle.MONTHLY:
            new_amount = new_plan.monthly_plan_cost
        elif subscription.billing_cycle == BillingCycle.YEARLY:
            new_amount = new_plan.yearly_plan_cost
        else:
            new_amount = new_plan.monthly_plan_cost

        # Determine if upgrade or downgrade
        is_upgrade = new_amount > subscription.amount

        # Calculate proration
        proration = self.calculate_proration(subscription, new_plan)

        # Determine effective date
        if is_upgrade:
            effective_date = datetime.now(timezone.utc)
            effective_note = "Immediate (upgrades are applied right away)"
        else:
            effective_date = subscription.current_period_end
            effective_note = f"End of billing period ({effective_date.strftime('%Y-%m-%d')})"

        return {
            "current_plan": {
                "id": current_plan.id,
                "name": current_plan.name,
                "amount": float(subscription.amount),
                "features": {
                    "max_documents": current_plan.max_documents,
                    "max_websites": current_plan.max_websites,
                    "monthly_chats": current_plan.monthly_chats
                }
            },
            "new_plan": {
                "id": new_plan.id,
                "name": new_plan.name,
                "amount": float(new_amount),
                "features": {
                    "max_documents": new_plan.max_documents,
                    "max_websites": new_plan.max_websites,
                    "monthly_chats": new_plan.monthly_chats
                }
            },
            "change_type": "upgrade" if is_upgrade else "downgrade",
            "proration": proration,
            "effective_date": effective_date.isoformat(),
            "effective_note": effective_note,
            "billing_cycle": subscription.billing_cycle.value,
            "currency": subscription.currency,
            "requires_immediate_payment": is_upgrade and proration["proration_amount"] > 0,
            "payment_amount": proration["proration_amount"] if is_upgrade and proration["proration_amount"] > 0 else 0
        }

    async def cancel_subscription(
        self,
        subscription_id: str,
        reason: Optional[str] = None,
        cancel_immediately: bool = False,
        user_email: Optional[str] = None,
        user_full_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Cancel a subscription.

        By default, cancellation is scheduled for end of billing period.
        User retains access until period ends.

        Args:
            subscription_id: Subscription to cancel
            reason: Cancellation reason (for analytics)
            cancel_immediately: If True, cancel access immediately
            user_email: User email for notifications
            user_full_name: User name for notifications

        Returns:
            Dict with cancellation details
        """
        subscription = self.db.query(Subscription).filter(
            Subscription.id == subscription_id
        ).first()

        if not subscription:
            raise ValueError("Subscription not found")

        if subscription.status == SubscriptionStatus.CANCELLED:
            raise ValueError("Subscription is already cancelled")

        plan = self.db.query(Plan).filter(Plan.id == subscription.plan_id).first()

        if cancel_immediately:
            # Immediate cancellation
            subscription.status = SubscriptionStatus.CANCELLED
            subscription.cancelled_at = datetime.now(timezone.utc)
            subscription.cancellation_reason = reason
            subscription.ends_at = datetime.now(timezone.utc)
            effective_date = datetime.now(timezone.utc)
            message = "Subscription cancelled immediately"
        else:
            # Cancel at period end
            subscription.cancel_at_period_end = True
            subscription.cancellation_reason = reason
            effective_date = subscription.current_period_end
            message = f"Subscription will be cancelled on {effective_date.strftime('%Y-%m-%d')}"

        subscription.auto_renew = False
        subscription.updated_at = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(subscription)

        logger.info(
            f"Subscription {'cancelled' if cancel_immediately else 'scheduled for cancellation'}",
            extra={
                "subscription_id": subscription_id,
                "plan": plan.name if plan else "Unknown",
                "effective_date": effective_date.isoformat(),
                "reason": reason
            }
        )

        # Send cancellation notification
        if user_email:
            try:
                await email_publisher.publish_subscription_cancelled_email(
                    tenant_id=subscription.tenant_id,
                    to_email=user_email,
                    to_name=user_full_name or "User",
                    plan_name=plan.name if plan else "subscription",
                    effective_date=effective_date,
                    immediate=cancel_immediately
                )
            except Exception as e:
                logger.error(f"Failed to send cancellation notification: {e}", exc_info=True)

        return {
            "success": True,
            "message": message,
            "subscription_id": subscription.id,
            "plan_name": plan.name if plan else "Unknown",
            "cancel_immediately": cancel_immediately,
            "effective_date": effective_date.isoformat(),
            "access_until": effective_date.isoformat(),
            "reason": reason
        }

    def process_pending_plan_changes(self) -> Dict[str, Any]:
        """
        Process all pending plan changes that are due.

        Called by scheduled job to apply downgrades at end of billing period.

        Returns:
            Dict with processing results
        """
        now = datetime.now(timezone.utc)

        # Find all subscriptions with pending plan changes due today or earlier
        pending_subscriptions = self.db.query(Subscription).filter(
            Subscription.pending_plan_id.isnot(None),
            Subscription.pending_plan_effective_date <= now
        ).all()

        processed = 0
        failed = 0

        for subscription in pending_subscriptions:
            try:
                # Get pending plan
                new_plan = self.db.query(Plan).filter(
                    Plan.id == subscription.pending_plan_id
                ).first()

                if not new_plan:
                    logger.error(
                        f"Pending plan {subscription.pending_plan_id} not found for subscription {subscription.id}"
                    )
                    failed += 1
                    continue

                old_plan_id = subscription.plan_id

                # Apply the plan change
                subscription.plan_id = subscription.pending_plan_id

                # Update amount based on billing cycle
                if subscription.billing_cycle == BillingCycle.MONTHLY:
                    subscription.amount = new_plan.monthly_plan_cost
                elif subscription.billing_cycle == BillingCycle.YEARLY:
                    subscription.amount = new_plan.yearly_plan_cost

                # Clear pending change
                subscription.pending_plan_id = None
                subscription.pending_billing_cycle = None
                subscription.pending_plan_effective_date = None
                subscription.updated_at = now

                self.db.commit()
                processed += 1

                logger.info(
                    f"Applied pending plan change for subscription {subscription.id}",
                    extra={
                        "subscription_id": subscription.id,
                        "old_plan_id": old_plan_id,
                        "new_plan_id": new_plan.id
                    }
                )

                # Send downgrade notification email
                if subscription.user_email:
                    try:
                        # Get old plan for email
                        old_plan = self.db.query(Plan).filter(Plan.id == old_plan_id).first()

                        asyncio.run(email_publisher.publish_plan_downgraded_email(
                            tenant_id=subscription.tenant_id,
                            to_email=subscription.user_email,
                            to_name=subscription.user_full_name or "Valued Customer",
                            old_plan_name=old_plan.name if old_plan else "Previous Plan",
                            new_plan_name=new_plan.name,
                            effective_date=now
                        ))
                        logger.info(
                            f"Sent downgrade notification to {subscription.user_email} "
                            f"for subscription {subscription.id}"
                        )
                    except Exception as email_error:
                        # Don't fail the plan change if email fails
                        logger.error(
                            f"Failed to send downgrade notification for subscription {subscription.id}: {email_error}",
                            exc_info=True
                        )

            except Exception as e:
                logger.error(
                    f"Failed to process pending plan change for subscription {subscription.id}: {e}",
                    exc_info=True
                )
                failed += 1
                self.db.rollback()

        return {
            "processed": processed,
            "failed": failed,
            "total": len(pending_subscriptions)
        }
