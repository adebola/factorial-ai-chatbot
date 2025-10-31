"""
Background Job Scheduler

Uses APScheduler to run periodic tasks like gap detection and alert checking.
"""

import uuid
import asyncio
from datetime import datetime
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.database import SessionLocal
from app.core.config import settings
from app.core.logging_config import get_logger
from app.services.gap_detector import GapDetector
from app.services.alert_manager import AlertManager
from app.models.job_log import JobExecutionLog

logger = get_logger(__name__)


class BackgroundScheduler:
    """
    Manages scheduled background jobs using APScheduler.

    Jobs:
    - Gap detection: Daily or configured schedule
    - Quality alert checking: Hourly or configured schedule
    """

    def __init__(self):
        self.scheduler = AsyncIOScheduler(
            timezone="UTC",
            job_defaults={
                'coalesce': True,  # Combine multiple missed executions into one
                'max_instances': 1  # Only one instance of each job at a time
            }
        )
        self.is_running = False

    def start(self):
        """Start the scheduler and add jobs."""

        if not settings.ENABLE_SCHEDULER:
            logger.info("Scheduler is disabled via ENABLE_SCHEDULER setting")
            return

        try:
            # Add gap detection job
            if settings.ENABLE_GAP_DETECTION and settings.GAP_DETECTION_SCHEDULE:
                self._add_gap_detection_job()

            # Add quality check job
            if settings.QUALITY_CHECK_SCHEDULE:
                self._add_quality_check_job()

            # Start the scheduler
            self.scheduler.start()
            self.is_running = True

            logger.info(
                "Background scheduler started successfully",
                job_count=len(self.scheduler.get_jobs())
            )

        except Exception as e:
            logger.error(
                f"Failed to start background scheduler: {e}",
                exc_info=True
            )
            raise

    def stop(self):
        """Stop the scheduler gracefully."""

        if self.is_running:
            try:
                self.scheduler.shutdown(wait=True)
                self.is_running = False
                logger.info("Background scheduler stopped successfully")
            except Exception as e:
                logger.error(
                    f"Error stopping background scheduler: {e}",
                    exc_info=True
                )

    def _add_gap_detection_job(self):
        """Add gap detection job to scheduler."""

        try:
            # Parse cron schedule
            trigger = CronTrigger.from_crontab(settings.GAP_DETECTION_SCHEDULE)

            self.scheduler.add_job(
                func=self._run_gap_detection,
                trigger=trigger,
                id="gap_detection",
                name="Daily Knowledge Gap Detection",
                replace_existing=True
            )

            logger.info(
                "Gap detection job scheduled",
                schedule=settings.GAP_DETECTION_SCHEDULE
            )

        except Exception as e:
            logger.error(
                f"Failed to schedule gap detection job: {e}",
                schedule=settings.GAP_DETECTION_SCHEDULE,
                exc_info=True
            )

    def _add_quality_check_job(self):
        """Add quality alert checking job to scheduler."""

        try:
            # Parse cron schedule
            trigger = CronTrigger.from_crontab(settings.QUALITY_CHECK_SCHEDULE)

            self.scheduler.add_job(
                func=self._run_quality_check,
                trigger=trigger,
                id="quality_check",
                name="Periodic Quality Alert Check",
                replace_existing=True
            )

            logger.info(
                "Quality check job scheduled",
                schedule=settings.QUALITY_CHECK_SCHEDULE
            )

        except Exception as e:
            logger.error(
                f"Failed to schedule quality check job: {e}",
                schedule=settings.QUALITY_CHECK_SCHEDULE,
                exc_info=True
            )

    async def _run_gap_detection(self):
        """
        Run gap detection for all tenants.

        This job executes periodically (e.g., daily) to detect knowledge gaps
        across all tenants.
        """
        job_id = str(uuid.uuid4())
        start_time = datetime.now()

        logger.info("Starting scheduled gap detection job", job_id=job_id)

        db = SessionLocal()
        total_gaps = 0
        tenant_count = 0

        try:
            # Get all unique tenant IDs from quality metrics
            # (In production, you might query a tenants table instead)
            from app.models.quality_metrics import RAGQualityMetrics
            tenants = db.query(RAGQualityMetrics.tenant_id).distinct().all()
            tenant_ids = [t[0] for t in tenants]

            detector = GapDetector(db)

            for tenant_id in tenant_ids:
                try:
                    gaps = detector.detect_gaps(
                        tenant_id=tenant_id,
                        days_lookback=settings.GAP_DETECTION_LOOKBACK_DAYS
                    )
                    total_gaps += len(gaps)
                    tenant_count += 1

                    logger.info(
                        "Gap detection completed for tenant",
                        tenant_id=tenant_id,
                        gaps_detected=len(gaps)
                    )

                except Exception as e:
                    logger.error(
                        f"Gap detection failed for tenant: {e}",
                        tenant_id=tenant_id,
                        exc_info=True
                    )

            # Log job execution
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            job_log = JobExecutionLog(
                id=job_id,
                tenant_id=None,  # System-wide job
                job_name="gap_detection",
                job_type="gap_detection",
                status="success",
                started_at=start_time,
                completed_at=datetime.now(),
                duration_ms=duration_ms,
                result_summary={
                    "tenants_processed": tenant_count,
                    "total_gaps_detected": total_gaps
                },
                triggered_by="scheduler"
            )

            db.add(job_log)
            db.commit()

            logger.info(
                "Gap detection job completed successfully",
                job_id=job_id,
                tenants_processed=tenant_count,
                gaps_detected=total_gaps,
                duration_ms=duration_ms
            )

        except Exception as e:
            # Log failed job execution
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            job_log = JobExecutionLog(
                id=job_id,
                tenant_id=None,
                job_name="gap_detection",
                job_type="gap_detection",
                status="failed",
                started_at=start_time,
                completed_at=datetime.now(),
                duration_ms=duration_ms,
                error_message=str(e),
                triggered_by="scheduler"
            )

            db.add(job_log)
            db.commit()

            logger.error(
                f"Gap detection job failed: {e}",
                job_id=job_id,
                exc_info=True
            )

        finally:
            db.close()

    async def _run_quality_check(self):
        """
        Run quality alert checking for all tenants.

        This job executes periodically (e.g., hourly) to check if any alert
        rules have been triggered.
        """
        job_id = str(uuid.uuid4())
        start_time = datetime.now()

        logger.info("Starting scheduled quality check job", job_id=job_id)

        db = SessionLocal()
        total_alerts = 0

        try:
            alert_manager = AlertManager(db)

            # Check all rules for all tenants
            result = await alert_manager.check_all_rules(tenant_id=None)

            total_alerts = result["alerts_triggered"]

            # Log job execution
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            job_log = JobExecutionLog(
                id=job_id,
                tenant_id=None,  # System-wide job
                job_name="quality_check",
                job_type="quality_check",
                status="success",
                started_at=start_time,
                completed_at=datetime.now(),
                duration_ms=duration_ms,
                result_summary={
                    "rules_checked": result["total_rules_checked"],
                    "alerts_triggered": total_alerts
                },
                triggered_by="scheduler"
            )

            db.add(job_log)
            db.commit()

            logger.info(
                "Quality check job completed successfully",
                job_id=job_id,
                rules_checked=result["total_rules_checked"],
                alerts_triggered=total_alerts,
                duration_ms=duration_ms
            )

        except Exception as e:
            # Log failed job execution
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            job_log = JobExecutionLog(
                id=job_id,
                tenant_id=None,
                job_name="quality_check",
                job_type="quality_check",
                status="failed",
                started_at=start_time,
                completed_at=datetime.now(),
                duration_ms=duration_ms,
                error_message=str(e),
                triggered_by="scheduler"
            )

            db.add(job_log)
            db.commit()

            logger.error(
                f"Quality check job failed: {e}",
                job_id=job_id,
                exc_info=True
            )

        finally:
            db.close()

    def get_job_status(self) -> dict:
        """Get status of all scheduled jobs."""

        if not self.is_running:
            return {
                "scheduler_running": False,
                "jobs": []
            }

        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger)
            })

        return {
            "scheduler_running": True,
            "job_count": len(jobs),
            "jobs": jobs
        }


# Singleton instance
background_scheduler = BackgroundScheduler()
