"""
Subscription status and usage limit checking service.

This service provides comprehensive checks for:
- Subscription status validation (active, trial, expired, cancelled)
- Grace period enforcement (3-day grace for failed payments)
- Usage limit validation against plan limits
- Account access permissions

Used by other services (chat, onboarding) to enforce subscription restrictions.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from sqlalchemy.orm import Session

from ..models.subscription import Subscription, SubscriptionStatus, UsageTracking
from ..models.plan import Plan

logger = logging.getLogger(__name__)


class SubscriptionRestrictionError(Exception):
    """Raised when subscription restrictions prevent an action"""

    def __init__(self, message: str, restriction_type: str, details: dict = None):
        super().__init__(message)
        self.restriction_type = restriction_type  # e.g., "expired", "usage_limit", "cancelled"
        self.details = details or {}


class SubscriptionChecker:
    """Service for checking subscription status and enforcing restrictions"""

    # Grace period for expired subscriptions (days)
    GRACE_PERIOD_DAYS = 3

    def __init__(self, db: Session):
        self.db = db

    def get_active_subscription(self, tenant_id: str) -> Optional[Subscription]:
        """
        Get active subscription for tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            Active subscription or None
        """
        return self.db.query(Subscription).filter(
            Subscription.tenant_id == tenant_id,
            Subscription.status.in_([
                SubscriptionStatus.ACTIVE,
                SubscriptionStatus.TRIALING,
                SubscriptionStatus.PAST_DUE  # Include past_due in grace period
            ])
        ).first()

    def check_subscription_active(
        self,
        tenant_id: str,
        include_grace_period: bool = True
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if tenant has an active subscription.

        Args:
            tenant_id: Tenant ID
            include_grace_period: Whether to allow grace period for expired subs

        Returns:
            Tuple of (is_active, reason_if_not_active)
        """
        subscription = self.db.query(Subscription).filter(
            Subscription.tenant_id == tenant_id
        ).first()

        if not subscription:
            return False, "No subscription found for this tenant"

        # Check status
        if subscription.status == SubscriptionStatus.ACTIVE:
            return True, None

        if subscription.status == SubscriptionStatus.TRIALING:
            # Check if trial has expired
            if subscription.trial_ends_at and subscription.trial_ends_at < datetime.now(timezone.utc):
                return False, "Trial period has expired"
            return True, None

        if subscription.status == SubscriptionStatus.PAST_DUE and include_grace_period:
            # Check grace period (3 days from current_period_end)
            if subscription.current_period_end:
                grace_end = subscription.current_period_end + timedelta(days=self.GRACE_PERIOD_DAYS)
                if datetime.now(timezone.utc) <= grace_end:
                    logger.info(
                        f"Subscription in grace period for tenant {tenant_id}",
                        extra={
                            "tenant_id": tenant_id,
                            "grace_ends": grace_end.isoformat()
                        }
                    )
                    return True, None
            return False, f"Subscription past due and grace period ({self.GRACE_PERIOD_DAYS} days) has expired"

        if subscription.status == SubscriptionStatus.CANCELLED:
            # Check if cancellation is effective yet (end of current period)
            if subscription.current_period_end and datetime.now(timezone.utc) <= subscription.current_period_end:
                return True, None
            return False, "Subscription has been cancelled"

        if subscription.status == SubscriptionStatus.EXPIRED:
            return False, "Subscription has expired"

        return False, f"Subscription status is {subscription.status}"

    def check_can_upload_document(self, tenant_id: str) -> Tuple[bool, Optional[str]]:
        """
        Check if tenant can upload a document based on plan limits.

        Args:
            tenant_id: Tenant ID

        Returns:
            Tuple of (can_upload, reason_if_not)
        """
        # First check subscription is active
        is_active, reason = self.check_subscription_active(tenant_id)
        if not is_active:
            return False, reason

        # Get subscription and plan
        subscription = self.get_active_subscription(tenant_id)
        if not subscription or not subscription.plan_id:
            return False, "No active plan found"

        plan = self.db.query(Plan).filter(Plan.id == subscription.plan_id).first()
        if not plan:
            return False, "Plan not found"

        # Get usage tracking
        usage = self.db.query(UsageTracking).filter(
            UsageTracking.subscription_id == subscription.id
        ).first()

        if not usage:
            # No usage record yet - allow upload
            return True, None

        # Check document limit
        if plan.document_limit is not None:
            if usage.documents_uploaded >= plan.document_limit:
                return False, f"Document limit reached ({plan.document_limit} documents allowed on {plan.name} plan)"

        return True, None

    def check_can_ingest_website(self, tenant_id: str) -> Tuple[bool, Optional[str]]:
        """
        Check if tenant can ingest a website based on plan limits.

        Args:
            tenant_id: Tenant ID

        Returns:
            Tuple of (can_ingest, reason_if_not)
        """
        # First check subscription is active
        is_active, reason = self.check_subscription_active(tenant_id)
        if not is_active:
            return False, reason

        # Get subscription and plan
        subscription = self.get_active_subscription(tenant_id)
        if not subscription or not subscription.plan_id:
            return False, "No active plan found"

        plan = self.db.query(Plan).filter(Plan.id == subscription.plan_id).first()
        if not plan:
            return False, "Plan not found"

        # Get usage tracking
        usage = self.db.query(UsageTracking).filter(
            UsageTracking.subscription_id == subscription.id
        ).first()

        if not usage:
            # No usage record yet - allow ingestion
            return True, None

        # Check website limit
        if plan.website_limit is not None:
            if usage.websites_ingested >= plan.website_limit:
                return False, f"Website limit reached ({plan.website_limit} websites allowed on {plan.name} plan)"

        return True, None

    def check_can_send_chat(self, tenant_id: str) -> Tuple[bool, Optional[str]]:
        """
        Check if tenant can send a chat message based on plan limits.

        Args:
            tenant_id: Tenant ID

        Returns:
            Tuple of (can_chat, reason_if_not)
        """
        # First check subscription is active
        is_active, reason = self.check_subscription_active(tenant_id)
        if not is_active:
            return False, reason

        # Get subscription and plan
        subscription = self.get_active_subscription(tenant_id)
        if not subscription or not subscription.plan_id:
            return False, "No active plan found"

        plan = self.db.query(Plan).filter(Plan.id == subscription.plan_id).first()
        if not plan:
            return False, "Plan not found"

        # Get usage tracking
        usage = self.db.query(UsageTracking).filter(
            UsageTracking.subscription_id == subscription.id
        ).first()

        if not usage:
            # No usage record yet - allow chat
            return True, None

        # Check monthly chat limit
        if plan.monthly_chat_limit is not None:
            if usage.monthly_chats_used >= plan.monthly_chat_limit:
                return False, f"Monthly chat limit reached ({plan.monthly_chat_limit} chats allowed on {plan.name} plan)"

        return True, None

    def get_usage_summary(self, tenant_id: str) -> Optional[dict]:
        """
        Get comprehensive usage summary for a tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            Dictionary with usage details or None
        """
        subscription = self.get_active_subscription(tenant_id)
        if not subscription:
            return None

        plan = self.db.query(Plan).filter(Plan.id == subscription.plan_id).first()
        if not plan:
            return None

        usage = self.db.query(UsageTracking).filter(
            UsageTracking.subscription_id == subscription.id
        ).first()

        if not usage:
            # No usage yet - return limits only
            return {
                "subscription_status": subscription.status.value,
                "plan_name": plan.name,
                "documents": {
                    "used": 0,
                    "limit": plan.document_limit,
                    "remaining": plan.document_limit
                },
                "websites": {
                    "used": 0,
                    "limit": plan.website_limit,
                    "remaining": plan.website_limit
                },
                "monthly_chats": {
                    "used": 0,
                    "limit": plan.monthly_chat_limit,
                    "remaining": plan.monthly_chat_limit
                }
            }

        return {
            "subscription_status": subscription.status.value,
            "plan_name": plan.name,
            "documents": {
                "used": usage.documents_uploaded,
                "limit": plan.document_limit,
                "remaining": max(0, plan.document_limit - usage.documents_uploaded) if plan.document_limit else None
            },
            "websites": {
                "used": usage.websites_ingested,
                "limit": plan.website_limit,
                "remaining": max(0, plan.website_limit - usage.websites_ingested) if plan.website_limit else None
            },
            "monthly_chats": {
                "used": usage.monthly_chats_used,
                "limit": plan.monthly_chat_limit,
                "remaining": max(0, plan.monthly_chat_limit - usage.monthly_chats_used) if plan.monthly_chat_limit else None,
                "resets_at": usage.monthly_reset_at.isoformat() if usage.monthly_reset_at else None
            }
        }

    def enforce_subscription_active(self, tenant_id: str):
        """
        Enforce that subscription is active, raise exception if not.

        Args:
            tenant_id: Tenant ID

        Raises:
            SubscriptionRestrictionError: If subscription is not active
        """
        is_active, reason = self.check_subscription_active(tenant_id)
        if not is_active:
            raise SubscriptionRestrictionError(
                message=reason,
                restriction_type="subscription_inactive",
                details={"tenant_id": tenant_id}
            )

    def enforce_can_upload_document(self, tenant_id: str):
        """
        Enforce document upload permission, raise exception if not allowed.

        Args:
            tenant_id: Tenant ID

        Raises:
            SubscriptionRestrictionError: If document upload not allowed
        """
        can_upload, reason = self.check_can_upload_document(tenant_id)
        if not can_upload:
            raise SubscriptionRestrictionError(
                message=reason,
                restriction_type="document_limit_exceeded",
                details={"tenant_id": tenant_id}
            )

    def enforce_can_ingest_website(self, tenant_id: str):
        """
        Enforce website ingestion permission, raise exception if not allowed.

        Args:
            tenant_id: Tenant ID

        Raises:
            SubscriptionRestrictionError: If website ingestion not allowed
        """
        can_ingest, reason = self.check_can_ingest_website(tenant_id)
        if not can_ingest:
            raise SubscriptionRestrictionError(
                message=reason,
                restriction_type="website_limit_exceeded",
                details={"tenant_id": tenant_id}
            )

    def enforce_can_send_chat(self, tenant_id: str):
        """
        Enforce chat permission, raise exception if not allowed.

        Args:
            tenant_id: Tenant ID

        Raises:
            SubscriptionRestrictionError: If chat not allowed
        """
        can_chat, reason = self.check_can_send_chat(tenant_id)
        if not can_chat:
            raise SubscriptionRestrictionError(
                message=reason,
                restriction_type="chat_limit_exceeded",
                details={"tenant_id": tenant_id}
            )
