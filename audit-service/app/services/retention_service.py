"""Scheduled retention cleanup for audit events.

Deletes events where retention_days is set and the event has expired.
Runs daily at 2am via APScheduler.
"""
from datetime import datetime, timezone, timedelta
from sqlalchemy import and_

from ..core.database import SessionLocal
from ..core.logging_config import get_logger
from ..models.audit_event import AuditEvent

logger = get_logger("retention")

BATCH_SIZE = 1000


def run_retention_cleanup():
    """Delete expired audit events in batches."""
    db = SessionLocal()
    total_deleted = 0
    try:
        now = datetime.now(timezone.utc)
        while True:
            # Find expired events
            expired = (
                db.query(AuditEvent)
                .filter(
                    AuditEvent.retention_days.isnot(None),
                    AuditEvent.created_at < now - timedelta(days=1)  # at least 1 day old
                )
                .limit(BATCH_SIZE)
                .all()
            )

            if not expired:
                break

            batch_deleted = 0
            for event in expired:
                age_days = (now - event.created_at).days if event.created_at else 0
                if age_days >= event.retention_days:
                    db.delete(event)
                    batch_deleted += 1

            db.commit()
            total_deleted += batch_deleted

            if batch_deleted < BATCH_SIZE:
                break

        if total_deleted > 0:
            logger.info(f"Retention cleanup: deleted {total_deleted} expired audit events")
        else:
            logger.debug("Retention cleanup: no expired events found")

    except Exception as e:
        db.rollback()
        logger.error(f"Retention cleanup failed: {e}")
    finally:
        db.close()
