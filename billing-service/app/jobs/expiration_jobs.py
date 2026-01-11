"""
Scheduled jobs for checking trial and subscription expirations.

These jobs run periodically to:
- Warn users before trials/subscriptions expire
- Notify users when trials/subscriptions have expired
- Update subscription statuses
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import and_

from ..core.database import SessionLocal
from ..core.redis_lock import distributed_lock
from ..models.subscription import Subscription, SubscriptionStatus, UsageTracking
from ..services.email_publisher import email_publisher
from ..services.notification_service import NotificationService
from ..services.plan_management_service import PlanManagementService

logger = logging.getLogger(__name__)


def check_trial_expirations_3day():
    """
    Check for trials expiring in 3 days and send warning emails.

    Runs: Daily at 9:00 AM
    Lock: Prevents duplicate execution across multiple instances
    """
    with distributed_lock("check_trial_expirations_3day", timeout=600) as acquired:
        if not acquired:
            logger.info("Trial expiration check (3-day) already running on another instance")
            return

        logger.info("Starting trial expiration check (3-day warning)")
        db = SessionLocal()

        try:
            # Find trials expiring in exactly 3 days
            target_date = datetime.now(timezone.utc) + timedelta(days=3)
            start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = start_of_day + timedelta(days=1)

            expiring_trials = db.query(Subscription).filter(
                and_(
                    Subscription.status == SubscriptionStatus.TRIALING,
                    Subscription.trial_ends_at >= start_of_day,
                    Subscription.trial_ends_at < end_of_day,
                    Subscription.user_email.isnot(None)  # Must have email
                )
            ).all()

            logger.info(f"Found {len(expiring_trials)} trials expiring in 3 days")

            notification_service = NotificationService(db)
            sent_count = 0

            for subscription in expiring_trials:
                # Check if already notified
                if notification_service.check_already_notified(
                    tenant_id=subscription.tenant_id,
                    subscription_id=subscription.id,
                    notification_type="trial_expiring_3day",
                    within_hours=48  # Don't send again within 48 hours
                ):
                    logger.debug(f"Skipping duplicate notification for subscription {subscription.id}")
                    continue

                # Send email notification
                try:
                    success = asyncio.run(email_publisher.publish_trial_expiring_email(
                        tenant_id=subscription.tenant_id,
                        to_email=subscription.user_email,
                        to_name=subscription.user_full_name or "User",
                        days_remaining=3
                    ))

                    if success:
                        # Log notification
                        notification_service.log_notification(
                            tenant_id=subscription.tenant_id,
                            subscription_id=subscription.id,
                            notification_type="trial_expiring_3day",
                            recipient_email=subscription.user_email,
                            recipient_name=subscription.user_full_name or "User",
                            subject=f"Your ChatCraft Trial Expires in 3 Days",
                            template_used="trial_expiring_email",
                            metadata={
                                "days_remaining": 3,
                                "trial_ends_at": subscription.trial_ends_at.isoformat()
                            }
                        )
                        sent_count += 1
                        logger.info(f"Sent trial expiring notification to {subscription.user_email}")
                    else:
                        logger.error(f"Failed to send trial expiring email to {subscription.user_email}")

                except Exception as e:
                    logger.error(
                        f"Error sending trial expiring notification: {e}",
                        exc_info=True,
                        extra={"subscription_id": subscription.id}
                    )

            logger.info(f"Trial expiration check complete: {sent_count}/{len(expiring_trials)} emails sent")

        except Exception as e:
            logger.error(f"Error in trial expiration check (3-day): {e}", exc_info=True)

        finally:
            db.close()


def check_trial_expired():
    """
    Check for expired trials and send notification + update status.

    Runs: Daily at 10:00 AM
    Lock: Prevents duplicate execution across multiple instances
    """
    with distributed_lock("check_trial_expired", timeout=600) as acquired:
        if not acquired:
            logger.info("Trial expired check already running on another instance")
            return

        logger.info("Starting trial expired check")
        db = SessionLocal()

        try:
            # Find trials that have expired (ended before now)
            now = datetime.now(timezone.utc)

            expired_trials = db.query(Subscription).filter(
                and_(
                    Subscription.status == SubscriptionStatus.TRIALING,
                    Subscription.trial_ends_at < now,
                    Subscription.user_email.isnot(None)
                )
            ).all()

            logger.info(f"Found {len(expired_trials)} expired trials")

            notification_service = NotificationService(db)
            processed_count = 0

            for subscription in expired_trials:
                try:
                    # Update subscription status to EXPIRED
                    subscription.status = SubscriptionStatus.EXPIRED

                    # Ensure period markers are consistent
                    # If current_period_end is beyond trial_ends_at, fix it
                    if subscription.current_period_end > subscription.trial_ends_at:
                        subscription.current_period_end = subscription.trial_ends_at
                        subscription.ends_at = subscription.trial_ends_at

                    db.commit()

                    # Check if already notified
                    if notification_service.check_already_notified(
                        tenant_id=subscription.tenant_id,
                        subscription_id=subscription.id,
                        notification_type="trial_expired",
                        within_hours=72  # Don't send again within 72 hours
                    ):
                        logger.debug(f"Skipping duplicate notification for subscription {subscription.id}")
                        continue

                    # Send email notification
                    success = asyncio.run(email_publisher.publish_trial_expired_email(
                        tenant_id=subscription.tenant_id,
                        to_email=subscription.user_email,
                        to_name=subscription.user_full_name or "User"
                    ))

                    if success:
                        # Log notification
                        notification_service.log_notification(
                            tenant_id=subscription.tenant_id,
                            subscription_id=subscription.id,
                            notification_type="trial_expired",
                            recipient_email=subscription.user_email,
                            recipient_name=subscription.user_full_name or "User",
                            subject="Your ChatCraft Trial Has Expired",
                            template_used="trial_expired_email",
                            metadata={
                                "trial_ended_at": subscription.trial_ends_at.isoformat()
                            }
                        )
                        processed_count += 1
                        logger.info(f"Sent trial expired notification to {subscription.user_email}")
                    else:
                        logger.error(f"Failed to send trial expired email to {subscription.user_email}")

                except Exception as e:
                    logger.error(
                        f"Error processing expired trial: {e}",
                        exc_info=True,
                        extra={"subscription_id": subscription.id}
                    )
                    db.rollback()

            logger.info(f"Trial expired check complete: {processed_count}/{len(expired_trials)} processed")

        except Exception as e:
            logger.error(f"Error in trial expired check: {e}", exc_info=True)

        finally:
            db.close()


def check_subscription_expirations_7day():
    """
    Check for subscriptions expiring in 7 days and send warning emails.

    Runs: Daily at 9:00 AM
    Lock: Prevents duplicate execution across multiple instances
    """
    with distributed_lock("check_subscription_expirations_7day", timeout=600) as acquired:
        if not acquired:
            logger.info("Subscription expiration check (7-day) already running on another instance")
            return

        logger.info("Starting subscription expiration check (7-day warning)")
        db = SessionLocal()

        try:
            # Find subscriptions expiring in exactly 7 days
            target_date = datetime.now(timezone.utc) + timedelta(days=7)
            start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = start_of_day + timedelta(days=1)

            expiring_subscriptions = db.query(Subscription).filter(
                and_(
                    Subscription.status == SubscriptionStatus.ACTIVE,
                    Subscription.current_period_end >= start_of_day,
                    Subscription.current_period_end < end_of_day,
                    Subscription.user_email.isnot(None)
                )
            ).all()

            logger.info(f"Found {len(expiring_subscriptions)} subscriptions expiring in 7 days")

            notification_service = NotificationService(db)
            sent_count = 0

            for subscription in expiring_subscriptions:
                # Check if already notified
                if notification_service.check_already_notified(
                    tenant_id=subscription.tenant_id,
                    subscription_id=subscription.id,
                    notification_type="subscription_expiring_7day",
                    within_hours=120  # Don't send again within 5 days
                ):
                    logger.debug(f"Skipping duplicate notification for subscription {subscription.id}")
                    continue

                # Get plan name (if available)
                plan_name = "subscription"  # Default fallback
                # TODO: Join with Plan table to get actual plan name when needed

                # Send email notification
                try:
                    success = asyncio.run(email_publisher.publish_subscription_expiring_email(
                        tenant_id=subscription.tenant_id,
                        to_email=subscription.user_email,
                        to_name=subscription.user_full_name or "User",
                        plan_name=plan_name,
                        days_remaining=7
                    ))

                    if success:
                        # Log notification
                        notification_service.log_notification(
                            tenant_id=subscription.tenant_id,
                            subscription_id=subscription.id,
                            notification_type="subscription_expiring_7day",
                            recipient_email=subscription.user_email,
                            recipient_name=subscription.user_full_name or "User",
                            subject=f"Your ChatCraft {plan_name} Subscription Expires in 7 Days",
                            template_used="subscription_expiring_email",
                            metadata={
                                "days_remaining": 7,
                                "expires_at": subscription.current_period_end.isoformat()
                            }
                        )
                        sent_count += 1
                        logger.info(f"Sent subscription expiring notification to {subscription.user_email}")
                    else:
                        logger.error(f"Failed to send subscription expiring email to {subscription.user_email}")

                except Exception as e:
                    logger.error(
                        f"Error sending subscription expiring notification: {e}",
                        exc_info=True,
                        extra={"subscription_id": subscription.id}
                    )

            logger.info(f"Subscription expiration check complete: {sent_count}/{len(expiring_subscriptions)} emails sent")

        except Exception as e:
            logger.error(f"Error in subscription expiration check (7-day): {e}", exc_info=True)

        finally:
            db.close()


def check_subscription_expired():
    """
    Check for expired subscriptions and send notification + update status.

    Runs: Daily at 10:00 AM
    Lock: Prevents duplicate execution across multiple instances
    """
    with distributed_lock("check_subscription_expired", timeout=600) as acquired:
        if not acquired:
            logger.info("Subscription expired check already running on another instance")
            return

        logger.info("Starting subscription expired check")
        db = SessionLocal()

        try:
            # Find subscriptions that have expired (ended before now)
            # NOTE: Mark ALL subscriptions as expired when period ends, regardless of auto_renew
            # The auto_renew flag should control AUTOMATIC renewal behavior, not expiration detection
            now = datetime.now(timezone.utc)

            expired_subscriptions = db.query(Subscription).filter(
                and_(
                    Subscription.status == SubscriptionStatus.ACTIVE,
                    Subscription.current_period_end < now,
                    Subscription.user_email.isnot(None)
                )
            ).all()

            logger.info(f"Found {len(expired_subscriptions)} expired subscriptions")

            notification_service = NotificationService(db)
            processed_count = 0

            for subscription in expired_subscriptions:
                try:
                    # Update subscription status to EXPIRED
                    subscription.status = SubscriptionStatus.EXPIRED
                    db.commit()

                    # Check if already notified
                    if notification_service.check_already_notified(
                        tenant_id=subscription.tenant_id,
                        subscription_id=subscription.id,
                        notification_type="subscription_expired",
                        within_hours=72  # Don't send again within 72 hours
                    ):
                        logger.debug(f"Skipping duplicate notification for subscription {subscription.id}")
                        continue

                    # Get plan name (if available)
                    plan_name = "subscription"  # Default fallback

                    # Send email notification
                    success = asyncio.run(email_publisher.publish_subscription_expired_email(
                        tenant_id=subscription.tenant_id,
                        to_email=subscription.user_email,
                        to_name=subscription.user_full_name or "User",
                        plan_name=plan_name
                    ))

                    if success:
                        # Log notification
                        notification_service.log_notification(
                            tenant_id=subscription.tenant_id,
                            subscription_id=subscription.id,
                            notification_type="subscription_expired",
                            recipient_email=subscription.user_email,
                            recipient_name=subscription.user_full_name or "User",
                            subject=f"Your ChatCraft {plan_name} Subscription Has Expired",
                            template_used="subscription_expired_email",
                            metadata={
                                "expired_at": subscription.current_period_end.isoformat()
                            }
                        )
                        processed_count += 1
                        logger.info(f"Sent subscription expired notification to {subscription.user_email}")
                    else:
                        logger.error(f"Failed to send subscription expired email to {subscription.user_email}")

                except Exception as e:
                    logger.error(
                        f"Error processing expired subscription: {e}",
                        exc_info=True,
                        extra={"subscription_id": subscription.id}
                    )
                    db.rollback()

            logger.info(f"Subscription expired check complete: {processed_count}/{len(expired_subscriptions)} processed")

        except Exception as e:
            logger.error(f"Error in subscription expired check: {e}", exc_info=True)

        finally:
            db.close()


def reset_monthly_usage():
    """
    Reset monthly usage counters on the 1st of each month.

    Runs: Monthly on the 1st at 00:01 AM
    Lock: Prevents duplicate execution across multiple instances
    """
    with distributed_lock("reset_monthly_usage", timeout=1800) as acquired:
        if not acquired:
            logger.info("Monthly usage reset already running on another instance")
            return

        logger.info("Starting monthly usage reset")
        db = SessionLocal()

        try:
            now = datetime.now(timezone.utc)

            # Reset all usage tracking records
            usage_records = db.query(UsageTracking).all()

            logger.info(f"Resetting {len(usage_records)} usage records")

            for usage in usage_records:
                usage.monthly_chats_used = 0
                usage.monthly_reset_at = now

            db.commit()

            logger.info(f"Monthly usage reset complete: {len(usage_records)} records reset")

        except Exception as e:
            logger.error(f"Error in monthly usage reset: {e}", exc_info=True)
            db.rollback()

        finally:
            db.close()


def process_pending_plan_changes():
    """
    Process pending plan changes (downgrades scheduled for period end).

    Runs: Daily at 00:30 AM UTC
    Lock: Prevents duplicate execution across multiple instances
    """
    with distributed_lock("process_pending_plan_changes", timeout=600) as acquired:
        if not acquired:
            logger.info("Pending plan changes processing already running on another instance")
            return

        logger.info("Starting pending plan changes processing")
        db = SessionLocal()

        try:
            plan_mgmt = PlanManagementService(db)
            result = plan_mgmt.process_pending_plan_changes()

            logger.info(
                f"Pending plan changes processed: {result['processed']} successful, {result['failed']} failed",
                extra=result
            )

        except Exception as e:
            logger.error(f"Error processing pending plan changes: {e}", exc_info=True)

        finally:
            db.close()


def check_usage_warnings():
    """
    Check all active subscriptions for usage approaching limits and send warnings.

    Runs: Every 6 hours
    Lock: Prevents duplicate execution across multiple instances
    """
    with distributed_lock("check_usage_warnings", timeout=1800) as acquired:
        if not acquired:
            logger.info("Usage warning check already running on another instance")
            return

        logger.info("Starting usage warning check")
        db = SessionLocal()

        try:
            from ..services.usage_warning_service import UsageWarningService

            warning_service = UsageWarningService(db)
            result = warning_service.check_all_active_subscriptions()

            logger.info(
                f"Usage warning check complete: {result['warnings_sent']['total']} warnings sent to {result['subscriptions_warned']} subscriptions",
                extra=result
            )

        except Exception as e:
            logger.error(f"Error in usage warning check: {e}", exc_info=True)

        finally:
            db.close()
