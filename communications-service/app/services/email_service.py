import os
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

# Import SSL disabling module first (for development)
if os.environ.get("ENVIRONMENT", "development") == "development":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    try:
        import disable_ssl
    except ImportError:
        pass

import urllib3
from sendgrid import SendGridAPIClient, Content, Attachment, FileContent, FileName, FileType, Disposition
from sendgrid.helpers.mail import Mail, TrackingSettings, OpenTracking, ClickTracking
from sqlalchemy.orm import Session

from ..core.logging_config import get_logger, log_message_sent, log_message_failed
from ..models.communications import EmailMessage, MessageStatus, DeliveryLog, MessageType, TenantSettings

# Disable SSL warnings for development
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class EmailService:
    """Service for sending emails via SendGrid"""

    def __init__(self, db: Session):
        self.db = db
        self.logger = get_logger("email_service")

        # Get SendGrid configuration from environment
        self.api_key = os.environ.get("SENDGRID_API_KEY")

        if not self.api_key:
            raise ValueError("SENDGRID_API_KEY environment variable is not set")

        self.default_from_email = os.environ.get("SENDGRID_FROM_EMAIL", "noreply@example.com")
        self.default_from_name = os.environ.get("SENDGRID_FROM_NAME", "FactorialBot")

        # Initialize SendGrid client
        try:
            self.sg = SendGridAPIClient(api_key=self.api_key)
            self.logger.info("SendGrid client initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize SendGrid client: {e}")
            raise

    def send_email(
        self,
        tenant_id: str,
        to_email: str,
        subject: str,
        html_content: Optional[str] = None,
        text_content: Optional[str] = None,
        to_name: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        # template_id: Optional[str] = None,
        template_data: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, bool]:
        """
        Send an email via SendGrid

        Returns:
            Tuple of (message_id, success)
        """

        # Get tenant settings for rate limiting
        tenant_settings = self._get_tenant_settings(tenant_id)

        # Create email record in database
        email_record = EmailMessage(
            tenant_id=tenant_id,
            to_email=to_email,
            to_name=to_name,
            from_email=self.default_from_email,
            from_name=self.default_from_name,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            # template_id=template_id,
            # template_data=template_data,
            attachments=attachments,
            status=MessageStatus.PENDING
        )

        self.db.add(email_record)
        self.db.commit()
        self.db.refresh(email_record)

        try:
            # Check rate limits
            if not self._check_rate_limit(tenant_id, tenant_settings):
                self._update_email_status(email_record.id, MessageStatus.FAILED, "Rate limit exceeded")
                return email_record.id, False

            # Create SendGrid mail object
            mail = self._create_sendgrid_mail(
                from_email=self.default_from_email,
                from_name=self.default_from_name,
                to_email=to_email,
                to_name=to_name,
                subject=subject,
                html_content=html_content,
                text_content=text_content,
                attachments=attachments,
                tenant_settings=tenant_settings
            )

            # Send email via SendGrid
            response = self.sg.send(mail)

            if response.status_code in [200, 202]:
                # Success
                self._update_email_status(
                    email_record.id,
                    MessageStatus.SENT,
                    provider_id=response.headers.get('X-Message-Id'),
                    sent_at=datetime.utcnow()
                )

                # Update rate limit counter
                self._increment_rate_limit_counter(tenant_id, tenant_settings)

                # Log delivery
                self._log_delivery(
                    email_record.id,
                    MessageType.EMAIL,
                    tenant_id,
                    "sent",
                    {"status_code": response.status_code, "headers": dict(response.headers)}
                )

                log_message_sent(
                    message_type="email",
                    message_id=email_record.id,
                    tenant_id=tenant_id,
                    recipient=to_email,
                    provider="sendgrid",
                    subject=subject
                )

                return email_record.id, True

            else:
                # Failed
                error_msg = f"SendGrid API error: {response.status_code}"
                self._update_email_status(email_record.id, MessageStatus.FAILED, error_msg)

                log_message_failed(
                    message_type="email",
                    message_id=email_record.id,
                    tenant_id=tenant_id,
                    recipient=to_email,
                    error=error_msg
                )

                return email_record.id, False

        except Exception as e:
            # Exception occurred
            error_msg = f"Failed to send email: {str(e)}"
            self._update_email_status(email_record.id, MessageStatus.FAILED, error_msg)

            log_message_failed(
                message_type="email",
                message_id=email_record.id,
                tenant_id=tenant_id,
                recipient=to_email,
                error=error_msg
            )

            return email_record.id, False

    def _create_sendgrid_mail(
        self,
        from_email: str,
        from_name: str,
        to_email: str,
        to_name: Optional[str],
        subject: str,
        html_content: Optional[str],
        text_content: Optional[str],
        attachments: Optional[List[Dict[str, Any]]],
        tenant_settings: TenantSettings
    ) -> Mail:
        """Create SendGrid Mail object"""

        # Create mail object
        mail = Mail(
            from_email=from_email,
            to_emails=to_email,
            subject=subject
        )

        # Add content
        if html_content:
            mail.add_content(Content("text/html", html_content))
        if text_content:
            mail.add_content(Content("text/plain", text_content))

        # Add attachments if provided
        if attachments:
            for attachment_info in attachments:
                try:
                    attachment = self._create_attachment(attachment_info)
                    if attachment:
                        mail.add_attachment(attachment)
                except Exception as e:
                    self.logger.warning(f"Failed to add attachment: {e}")

        # Add tracking settings
        tracking_settings = TrackingSettings()

        if tenant_settings.enable_open_tracking:
            tracking_settings.open_tracking = OpenTracking(enable=True)

        if tenant_settings.enable_click_tracking:
            tracking_settings.click_tracking = ClickTracking(enable=True)

        mail.tracking_settings = tracking_settings

        return mail

    def _create_attachment(self, attachment_info: Dict[str, Any]) -> Optional[Attachment]:
        """Create SendGrid attachment from attachment info"""

        filename = attachment_info.get("filename")
        content = attachment_info.get("content")  # Base64 encoded content
        content_type = attachment_info.get("content_type")

        if not all([filename, content, content_type]):
            return None

        attachment = Attachment()
        attachment.file_content = FileContent(content)
        attachment.file_name = FileName(filename)
        attachment.file_type = FileType(content_type)
        attachment.disposition = Disposition("attachment")

        return attachment

    def _get_tenant_settings(self, tenant_id: str) -> TenantSettings:
        """Get or create tenant settings"""
        settings = self.db.query(TenantSettings).filter(
            TenantSettings.tenant_id == tenant_id
        ).first()

        if not settings:
            # Create default settings
            settings = TenantSettings(
                tenant_id=tenant_id,
                default_from_email=self.default_from_email,
                default_from_name=self.default_from_name
            )
            self.db.add(settings)
            self.db.commit()
            self.db.refresh(settings)

        return settings

    def _check_rate_limit(self, tenant_id: str, tenant_settings: TenantSettings) -> bool:
        """Check if tenant has exceeded daily email limit"""
        # Reset counter if it's a new day
        today = datetime.utcnow().date()
        if tenant_settings.limit_reset_date.date() < today:
            tenant_settings.emails_sent_today = 0
            tenant_settings.limit_reset_date = datetime.utcnow()
            self.db.commit()

        return tenant_settings.emails_sent_today < tenant_settings.daily_email_limit

    def _increment_rate_limit_counter(self, tenant_id: str, tenant_settings: TenantSettings):
        """Increment the daily email counter"""
        tenant_settings.emails_sent_today += 1
        self.db.commit()

    def _update_email_status(
        self,
        email_id: str,
        status: MessageStatus,
        error_message: Optional[str] = None,
        provider_id: Optional[str] = None,
        sent_at: Optional[datetime] = None,
        delivered_at: Optional[datetime] = None
    ):
        """Update email status in database"""
        email = self.db.query(EmailMessage).filter(EmailMessage.id == email_id).first()
        if email:
            email.status = status
            if error_message:
                email.error_message = error_message
            if provider_id:
                email.provider_id = provider_id
            if sent_at:
                email.sent_at = sent_at
            if delivered_at:
                email.delivered_at = delivered_at

            self.db.commit()

    def _log_delivery(
        self,
        message_id: str,
        message_type: MessageType,
        tenant_id: str,
        event_type: str,
        provider_response: Dict[str, Any]
    ):
        """Log delivery event"""
        log_entry = DeliveryLog(
            message_id=message_id,
            message_type=message_type,
            tenant_id=tenant_id,
            event_type=event_type,
            provider_name="sendgrid",
            provider_response=provider_response,
            occurred_at=datetime.utcnow()
        )

        self.db.add(log_entry)
        self.db.commit()

    def get_email_status(self, email_id: str, tenant_id: str) -> Optional[EmailMessage]:
        """Get email status for a specific tenant"""
        return self.db.query(EmailMessage).filter(
            EmailMessage.id == email_id,
            EmailMessage.tenant_id == tenant_id
        ).first()

    def get_tenant_emails(
        self,
        tenant_id: str,
        skip: int = 0,
        limit: int = 50,
        status: Optional[MessageStatus] = None
    ) -> List[EmailMessage]:
        """Get emails for a tenant with pagination"""
        query = self.db.query(EmailMessage).filter(EmailMessage.tenant_id == tenant_id)

        if status:
            query = query.filter(EmailMessage.status == status)

        return query.order_by(EmailMessage.created_at.desc()).offset(skip).limit(limit).all()

    def handle_webhook(self, webhook_data: List[Dict[str, Any]]) -> bool:
        """Handle SendGrid webhook events"""
        try:
            for event in webhook_data:
                event_type = event.get("event")
                email_id = event.get("email_id")  # Custom header we should add
                sg_message_id = event.get("sg_message_id")

                if not event_type:
                    continue

                # Find email by provider ID
                email = self.db.query(EmailMessage).filter(
                    EmailMessage.provider_id == sg_message_id
                ).first()

                if not email:
                    continue

                # Update email status based on event
                if event_type == "delivered":
                    self._update_email_status(
                        email.id,
                        MessageStatus.DELIVERED,
                        delivered_at=datetime.fromtimestamp(event.get("timestamp", 0))
                    )
                elif event_type == "bounce":
                    self._update_email_status(
                        email.id,
                        MessageStatus.BOUNCED,
                        error_message=event.get("reason", "Email bounced")
                    )
                elif event_type == "open":
                    email.opened_at = datetime.fromtimestamp(event.get("timestamp", 0))
                    self.db.commit()
                elif event_type == "click":
                    email.clicked_at = datetime.fromtimestamp(event.get("timestamp", 0))
                    self.db.commit()

                # Log the webhook event
                self._log_delivery(
                    email.id,
                    MessageType.EMAIL,
                    email.tenant_id,
                    event_type,
                    event
                )

            return True

        except Exception as e:
            self.logger.error(f"Failed to process webhook: {e}")
            return False