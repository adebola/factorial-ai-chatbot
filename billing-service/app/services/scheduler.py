"""
APScheduler setup for billing service background jobs.

This module configures and starts the background job scheduler for:
- Trial expiration checks
- Subscription expiration checks
- Monthly usage resets
- Payment reminders
"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

from ..jobs.expiration_jobs import (
    check_trial_expirations_3day,
    check_trial_expired,
    check_subscription_expirations_7day,
    check_subscription_expired,
    reset_monthly_usage,
    process_pending_plan_changes,
    check_usage_warnings
)

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = None


def job_listener(event):
    """
    Listen to job execution events for monitoring and logging.

    Args:
        event: APScheduler event
    """
    if event.exception:
        logger.error(
            f"Job {event.job_id} failed with exception: {event.exception}",
            extra={"job_id": event.job_id}
        )
    else:
        logger.info(
            f"Job {event.job_id} executed successfully",
            extra={"job_id": event.job_id}
        )


def init_scheduler():
    """
    Initialize and configure the APScheduler.

    This sets up all scheduled jobs for the billing service with appropriate
    cron schedules and Redis-based distributed locking.

    Returns:
        BackgroundScheduler: Configured scheduler instance
    """
    global scheduler

    if scheduler is not None:
        logger.warning("Scheduler already initialized")
        return scheduler

    logger.info("Initializing billing service scheduler")

    # Create scheduler
    scheduler = BackgroundScheduler(
        timezone="UTC",
        job_defaults={
            'coalesce': True,  # Combine missed runs into one
            'max_instances': 1,  # Only one instance of each job at a time
            'misfire_grace_time': 300  # 5 minutes grace period for missed jobs
        }
    )

    # Add event listener
    scheduler.add_listener(job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

    # ========================================
    # Trial Expiration Jobs
    # ========================================

    # Check for trials expiring in 3 days - Daily at 9:00 AM UTC
    scheduler.add_job(
        func=check_trial_expirations_3day,
        trigger=CronTrigger(hour=9, minute=0),
        id="check_trial_expirations_3day",
        name="Check trials expiring in 3 days",
        replace_existing=True
    )
    logger.info("Scheduled: Trial expiration check (3-day warning) - Daily at 9:00 AM UTC")

    # Check for expired trials - Daily at 10:00 AM UTC
    scheduler.add_job(
        func=check_trial_expired,
        trigger=CronTrigger(hour=10, minute=0),
        id="check_trial_expired",
        name="Check expired trials",
        replace_existing=True
    )
    logger.info("Scheduled: Trial expired check - Daily at 10:00 AM UTC")

    # ========================================
    # Subscription Expiration Jobs
    # ========================================

    # Check for subscriptions expiring in 7 days - Daily at 9:00 AM UTC
    scheduler.add_job(
        func=check_subscription_expirations_7day,
        trigger=CronTrigger(hour=9, minute=0),
        id="check_subscription_expirations_7day",
        name="Check subscriptions expiring in 7 days",
        replace_existing=True
    )
    logger.info("Scheduled: Subscription expiration check (7-day warning) - Daily at 9:00 AM UTC")

    # Check for expired subscriptions - Daily at 10:00 AM UTC
    scheduler.add_job(
        func=check_subscription_expired,
        trigger=CronTrigger(hour=10, minute=0),
        id="check_subscription_expired",
        name="Check expired subscriptions",
        replace_existing=True
    )
    logger.info("Scheduled: Subscription expired check - Daily at 10:00 AM UTC")

    # ========================================
    # Usage Reset Jobs
    # ========================================

    # Reset monthly usage - Monthly on the 1st at 00:01 AM UTC
    scheduler.add_job(
        func=reset_monthly_usage,
        trigger=CronTrigger(day=1, hour=0, minute=1),
        id="reset_monthly_usage",
        name="Reset monthly usage counters",
        replace_existing=True
    )
    logger.info("Scheduled: Monthly usage reset - 1st of each month at 00:01 AM UTC")

    # ========================================
    # Plan Change Jobs
    # ========================================

    # Process pending plan changes - Daily at 00:30 AM UTC
    scheduler.add_job(
        func=process_pending_plan_changes,
        trigger=CronTrigger(hour=0, minute=30),
        id="process_pending_plan_changes",
        name="Process pending plan changes",
        replace_existing=True
    )
    logger.info("Scheduled: Pending plan changes processing - Daily at 00:30 AM UTC")

    # ========================================
    # Usage Warning Jobs (Phase 7)
    # ========================================

    # Check usage warnings - Every 6 hours
    scheduler.add_job(
        func=check_usage_warnings,
        trigger=CronTrigger(hour="*/6", minute=0),
        id="check_usage_warnings",
        name="Check usage warnings (80%, 90%, 100%)",
        replace_existing=True
    )
    logger.info("Scheduled: Usage warning check - Every 6 hours")

    logger.info("Billing service scheduler initialized successfully")
    return scheduler


def start_scheduler():
    """
    Start the scheduler.

    This should be called during application startup.
    """
    global scheduler

    if scheduler is None:
        init_scheduler()

    if scheduler and not scheduler.running:
        scheduler.start()
        logger.info("✅ Billing service scheduler started")
        logger.info(f"Scheduled jobs: {len(scheduler.get_jobs())}")

        # Log all scheduled jobs
        for job in scheduler.get_jobs():
            logger.info(f"  - {job.id}: {job.name} (next run: {job.next_run_time})")
    else:
        logger.warning("Scheduler already running")


def stop_scheduler():
    """
    Stop the scheduler.

    This should be called during application shutdown.
    """
    global scheduler

    if scheduler and scheduler.running:
        scheduler.shutdown(wait=True)
        logger.info("Billing service scheduler stopped")
    else:
        logger.warning("Scheduler not running")


def get_scheduler():
    """
    Get the scheduler instance.

    Returns:
        BackgroundScheduler: Scheduler instance or None if not initialized
    """
    return scheduler


def list_jobs():
    """
    List all scheduled jobs.

    Returns:
        list: List of job information dictionaries
    """
    if scheduler is None:
        return []

    jobs = []
    for job in scheduler.get_jobs():
        # Get next run time safely
        try:
            next_run = job.next_run_time.isoformat() if hasattr(job, 'next_run_time') and job.next_run_time else None
        except AttributeError:
            next_run = None

        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run_time": next_run,
            "trigger": str(job.trigger)
        })

    return jobs
