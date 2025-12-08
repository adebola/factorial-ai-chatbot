"""
Notification service for managing email notification logs.

This service handles:
- Logging email notifications to the database
- Checking for duplicate notifications
- Preventing notification spam
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.orm import Session

from ..models.subscription import NotificationLog

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for managing notification logs"""

    def __init__(self, db: Session):
        self.db = db

    def check_already_notified(
        self,
        tenant_id: str,
        subscription_id: str,
        notification_type: str,
        within_hours: int = 24
    ) -> bool:
        """
        Check if a notification was already sent recently.

        Args:
            tenant_id: Tenant ID
            subscription_id: Subscription ID
            notification_type: Type of notification
            within_hours: Check within this many hours (default: 24)

        Returns:
            True if notification was already sent, False otherwise
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=within_hours)

        existing = self.db.query(NotificationLog).filter(
            NotificationLog.tenant_id == tenant_id,
            NotificationLog.subscription_id == subscription_id,
            NotificationLog.notification_type == notification_type,
            NotificationLog.created_at >= cutoff_time,
            NotificationLog.status.in_(["pending", "sent", "delivered"])
        ).first()

        return existing is not None

    def log_notification(
        self,
        tenant_id: str,
        subscription_id: str,
        notification_type: str,
        recipient_email: str,
        recipient_name: str,
        subject: str,
        template_used: Optional[str] = None,
        related_payment_id: Optional[str] = None,
        related_invoice_id: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> NotificationLog:
        """
        Create a notification log record.

        Args:
            tenant_id: Tenant ID
            subscription_id: Subscription ID
            notification_type: Type of notification
            recipient_email: Email recipient
            recipient_name: Recipient name
            subject: Email subject
            template_used: Template identifier (optional)
            related_payment_id: Related payment ID (optional)
            related_invoice_id: Related invoice ID (optional)
            metadata: Additional metadata (optional)

        Returns:
            Created NotificationLog record
        """
        notification = NotificationLog(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            subscription_id=subscription_id,
            notification_type=notification_type,
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            subject=subject,
            template_used=template_used,
            status="pending",
            related_payment_id=related_payment_id,
            related_invoice_id=related_invoice_id,
            notification_metadata=metadata or {},
            retry_count=0,
            max_retries=3
        )

        self.db.add(notification)
        self.db.commit()
        self.db.refresh(notification)

        logger.info(
            f"Logged notification: {notification_type} to {recipient_email}",
            extra={
                "tenant_id": tenant_id,
                "subscription_id": subscription_id,
                "notification_type": notification_type
            }
        )

        return notification

    def mark_notification_sent(
        self,
        notification_id: str
    ) -> bool:
        """
        Mark a notification as sent.

        Args:
            notification_id: Notification log ID

        Returns:
            True if updated successfully
        """
        notification = self.db.query(NotificationLog).filter(
            NotificationLog.id == notification_id
        ).first()

        if not notification:
            return False

        notification.status = "sent"
        notification.sent_at = datetime.now(timezone.utc)
        self.db.commit()

        return True

    def mark_notification_failed(
        self,
        notification_id: str,
        failure_reason: str
    ) -> bool:
        """
        Mark a notification as failed.

        Args:
            notification_id: Notification log ID
            failure_reason: Reason for failure

        Returns:
            True if updated successfully
        """
        notification = self.db.query(NotificationLog).filter(
            NotificationLog.id == notification_id
        ).first()

        if not notification:
            return False

        notification.status = "failed"
        notification.failed_at = datetime.now(timezone.utc)
        notification.failure_reason = failure_reason
        notification.retry_count += 1
        self.db.commit()

        return True

    def get_notifications_to_retry(
        self,
        max_age_hours: int = 24
    ) -> list[NotificationLog]:
        """
        Get failed notifications that should be retried.

        Args:
            max_age_hours: Only retry notifications within this age

        Returns:
            List of notifications to retry
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

        return self.db.query(NotificationLog).filter(
            NotificationLog.status == "failed",
            NotificationLog.retry_count < NotificationLog.max_retries,
            NotificationLog.created_at >= cutoff_time
        ).all()
