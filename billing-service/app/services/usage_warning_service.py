"""
Usage Warning Notification Service

Monitors usage across all subscriptions and sends warning emails when users
approach their plan limits.

Features:
- Document upload warnings (80%, 90%, 100%)
- Website ingestion warnings (80%, 90%, 100%)
- Monthly chat warnings (80%, 90%, 100%)
- Intelligent deduplication (don't spam users)
- Upgrade prompts with clear call-to-action
"""
import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_

from ..models.subscription import (
    Subscription,
    SubscriptionStatus,
    UsageTracking
)
from ..models.plan import Plan
from ..services.email_publisher import email_publisher
from ..services.notification_service import NotificationService
from ..core.logging_config import get_logger

logger = get_logger("usage-warning-service")


class UsageWarningService:
    """Service for monitoring usage and sending warning notifications"""

    # Warning thresholds (percentage of limit)
    THRESHOLD_80 = 0.80
    THRESHOLD_90 = 0.90
    THRESHOLD_100 = 1.00

    # Notification cooldown periods (hours)
    COOLDOWN_80 = 24   # Don't send 80% warning more than once per day
    COOLDOWN_90 = 12   # Don't send 90% warning more than twice per day
    COOLDOWN_100 = 6   # Don't send 100% warning more than 4 times per day

    def __init__(self, db: Session):
        self.db = db
        self.notification_service = NotificationService(db)

    def calculate_usage_percentage(self, used: int, limit: int) -> float:
        """
        Calculate usage percentage.

        Args:
            used: Current usage count
            limit: Maximum limit (-1 for unlimited)

        Returns:
            Percentage as decimal (0.0 to 1.0+)
            Returns 0.0 if limit is unlimited
        """
        if limit == -1:  # Unlimited
            return 0.0

        if limit == 0:  # No limit allowed
            return 1.0 if used > 0 else 0.0

        return used / limit

    def get_threshold_level(self, percentage: float) -> Optional[str]:
        """
        Determine which threshold level has been crossed.

        Args:
            percentage: Usage percentage (0.0 to 1.0+)

        Returns:
            Threshold level: "80", "90", or "100"
            None if below all thresholds
        """
        if percentage >= self.THRESHOLD_100:
            return "100"
        elif percentage >= self.THRESHOLD_90:
            return "90"
        elif percentage >= self.THRESHOLD_80:
            return "80"
        else:
            return None

    def should_send_warning(
        self,
        tenant_id: str,
        subscription_id: str,
        usage_type: str,
        threshold_level: str
    ) -> bool:
        """
        Check if warning should be sent based on notification history.

        Args:
            tenant_id: Tenant ID
            subscription_id: Subscription ID
            usage_type: Type of usage (documents, websites, monthly_chats)
            threshold_level: Threshold level ("80", "90", "100")

        Returns:
            True if warning should be sent, False if recently sent
        """
        notification_type = f"usage_warning_{usage_type}_{threshold_level}"

        # Get cooldown period for this threshold
        if threshold_level == "100":
            cooldown_hours = self.COOLDOWN_100
        elif threshold_level == "90":
            cooldown_hours = self.COOLDOWN_90
        else:
            cooldown_hours = self.COOLDOWN_80

        # Check if already notified within cooldown period
        already_notified = self.notification_service.check_already_notified(
            tenant_id=tenant_id,
            subscription_id=subscription_id,
            notification_type=notification_type,
            within_hours=cooldown_hours
        )

        return not already_notified

    def send_usage_warning(
        self,
        subscription: Subscription,
        plan: Plan,
        usage_type: str,
        current_usage: int,
        limit: int,
        threshold_level: str
    ) -> bool:
        """
        Send usage warning email.

        Args:
            subscription: Subscription object
            plan: Plan object
            usage_type: Type of usage (documents, websites, monthly_chats)
            current_usage: Current usage count
            limit: Maximum limit
            threshold_level: Threshold level ("80", "90", "100")

        Returns:
            True if email sent successfully
        """
        if not subscription.user_email:
            logger.warning(
                f"Cannot send usage warning - no email for subscription {subscription.id}"
            )
            return False

        # Calculate percentage
        percentage = self.calculate_usage_percentage(current_usage, limit)

        # Determine warning severity
        if threshold_level == "100":
            severity = "critical"
            message = "You've reached your limit!"
        elif threshold_level == "90":
            severity = "high"
            message = "You're approaching your limit"
        else:
            severity = "medium"
            message = "You're using most of your quota"

        # Format usage type for display
        usage_display = {
            "documents": "document uploads",
            "websites": "website ingestions",
            "monthly_chats": "monthly chat messages"
        }.get(usage_type, usage_type)

        # Send email
        try:
            success = asyncio.run(email_publisher.publish_usage_warning_email(
                tenant_id=subscription.tenant_id,
                to_email=subscription.user_email,
                to_name=subscription.user_full_name or "Valued Customer",
                plan_name=plan.name,
                usage_type=usage_display,
                current_usage=current_usage,
                limit=limit,
                percentage=int(percentage * 100),
                threshold_level=threshold_level,
                severity=severity
            ))

            if success:
                # Log notification
                notification_type = f"usage_warning_{usage_type}_{threshold_level}"
                self.notification_service.log_notification(
                    tenant_id=subscription.tenant_id,
                    subscription_id=subscription.id,
                    notification_type=notification_type,
                    recipient_email=subscription.user_email,
                    recipient_name=subscription.user_full_name or "Valued Customer",
                    subject=f"ChatCraft {plan.name} - {message}",
                    template_used="usage_warning_email",
                    metadata={
                        "usage_type": usage_type,
                        "current_usage": current_usage,
                        "limit": limit,
                        "percentage": percentage,
                        "threshold_level": threshold_level
                    }
                )

                logger.info(
                    f"Sent {threshold_level}% usage warning for {usage_type}",
                    extra={
                        "subscription_id": subscription.id,
                        "tenant_id": subscription.tenant_id,
                        "usage_type": usage_type,
                        "threshold": threshold_level
                    }
                )

                return True
            else:
                logger.error(
                    f"Failed to send usage warning email",
                    extra={
                        "subscription_id": subscription.id,
                        "usage_type": usage_type
                    }
                )
                return False

        except Exception as e:
            logger.error(
                f"Error sending usage warning: {e}",
                exc_info=True,
                extra={
                    "subscription_id": subscription.id,
                    "usage_type": usage_type
                }
            )
            return False

    def check_subscription_usage(self, subscription: Subscription) -> Dict[str, Any]:
        """
        Check all usage types for a single subscription and send warnings if needed.

        Args:
            subscription: Subscription to check

        Returns:
            Dictionary with warning counts by type
        """
        warnings_sent = {
            "documents": 0,
            "websites": 0,
            "monthly_chats": 0,
            "total": 0
        }

        try:
            # Get plan
            plan = self.db.query(Plan).filter(Plan.id == subscription.plan_id).first()
            if not plan:
                logger.warning(f"Plan not found for subscription {subscription.id}")
                return warnings_sent

            # Get usage tracking
            usage = self.db.query(UsageTracking).filter(
                UsageTracking.subscription_id == subscription.id
            ).first()

            if not usage:
                logger.warning(f"Usage tracking not found for subscription {subscription.id}")
                return warnings_sent

            # Check each usage type
            usage_checks = [
                ("documents", usage.documents_used, plan.document_limit),
                ("websites", usage.websites_used, plan.website_limit),
                ("monthly_chats", usage.monthly_chats_used, plan.monthly_chat_limit)
            ]

            for usage_type, current_usage, limit in usage_checks:
                # Skip unlimited plans
                if limit == -1:
                    continue

                # Calculate percentage and threshold
                percentage = self.calculate_usage_percentage(current_usage, limit)
                threshold_level = self.get_threshold_level(percentage)

                # Send warning if threshold crossed and not recently sent
                if threshold_level and self.should_send_warning(
                    tenant_id=subscription.tenant_id,
                    subscription_id=subscription.id,
                    usage_type=usage_type,
                    threshold_level=threshold_level
                ):
                    success = self.send_usage_warning(
                        subscription=subscription,
                        plan=plan,
                        usage_type=usage_type,
                        current_usage=current_usage,
                        limit=limit,
                        threshold_level=threshold_level
                    )

                    if success:
                        warnings_sent[usage_type] += 1
                        warnings_sent["total"] += 1

        except Exception as e:
            logger.error(
                f"Error checking subscription usage: {e}",
                exc_info=True,
                extra={"subscription_id": subscription.id}
            )

        return warnings_sent

    def check_all_active_subscriptions(self) -> Dict[str, Any]:
        """
        Check usage for all active subscriptions and send warnings.

        This is called by the scheduled job.

        Returns:
            Summary of warnings sent
        """
        logger.info("Starting usage warning check for all active subscriptions")

        try:
            # Find all active/trialing subscriptions
            subscriptions = self.db.query(Subscription).filter(
                Subscription.status.in_([
                    SubscriptionStatus.ACTIVE.value,
                    SubscriptionStatus.TRIALING.value
                ])
            ).all()

            logger.info(f"Found {len(subscriptions)} active subscriptions to check")

            total_warnings = {
                "documents": 0,
                "websites": 0,
                "monthly_chats": 0,
                "total": 0
            }

            subscriptions_checked = 0
            subscriptions_warned = 0

            for subscription in subscriptions:
                # Skip if no email
                if not subscription.user_email:
                    continue

                warnings = self.check_subscription_usage(subscription)
                subscriptions_checked += 1

                if warnings["total"] > 0:
                    subscriptions_warned += 1
                    total_warnings["documents"] += warnings["documents"]
                    total_warnings["websites"] += warnings["websites"]
                    total_warnings["monthly_chats"] += warnings["monthly_chats"]
                    total_warnings["total"] += warnings["total"]

            logger.info(
                f"Usage warning check complete: {total_warnings['total']} warnings sent to {subscriptions_warned} subscriptions",
                extra={
                    "subscriptions_checked": subscriptions_checked,
                    "subscriptions_warned": subscriptions_warned,
                    "warnings_by_type": total_warnings
                }
            )

            return {
                "subscriptions_checked": subscriptions_checked,
                "subscriptions_warned": subscriptions_warned,
                "warnings_sent": total_warnings
            }

        except Exception as e:
            logger.error(
                f"Error in usage warning check: {e}",
                exc_info=True
            )
            return {
                "subscriptions_checked": 0,
                "subscriptions_warned": 0,
                "warnings_sent": {"documents": 0, "websites": 0, "monthly_chats": 0, "total": 0},
                "error": str(e)
            }
