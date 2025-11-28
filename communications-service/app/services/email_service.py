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
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
from sqlalchemy.orm import Session

from ..core.logging_config import get_logger, log_message_sent, log_message_failed
from ..models.communications import EmailMessage, MessageStatus, DeliveryLog, MessageType, TenantSettings

# Disable SSL warnings for development
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class EmailService:
    """Service for sending emails via Brevo (formerly Sendinblue)"""

    def __init__(self, db: Session):
        self.db = db
        self.logger = get_logger("email_service")

        # Get Brevo configuration from environment
        self.api_key = os.environ.get("BREVO_API_KEY")

        if not self.api_key:
            raise ValueError("BREVO_API_KEY environment variable is not set")

        self.default_from_email = os.environ.get("BREVO_FROM_EMAIL", "noreply@example.com")
        self.default_from_name = os.environ.get("BREVO_FROM_NAME", "ChatCraft")

        # Initialize Brevo client
        try:
            # Configure API key
            configuration = sib_api_v3_sdk.Configuration()
            configuration.api_key['api-key'] = self.api_key

            # Create API instance
            api_client = sib_api_v3_sdk.ApiClient(configuration)
            self.brevo_api = sib_api_v3_sdk.TransactionalEmailsApi(api_client)

            self.logger.info("Brevo client initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize Brevo client: {e}")
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
        Send an email via Brevo

        Returns:
            Tuple of (message_id, success)
        """

        # Get tenant settings for rate limiting
        tenant_settings = self._get_tenant_settings(tenant_id)

        # Create an email record in the database
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
            status=MessageStatus.PENDING,
            created_at=datetime.utcnow()  # Explicitly set to avoid NOT NULL violation
        )

        self.db.add(email_record)
        self.db.commit()
        self.db.refresh(email_record)

        try:
            # Check rate limits
            if not self._check_rate_limit(tenant_id, tenant_settings):
                self._update_email_status(email_record.id, MessageStatus.FAILED, "Rate limit exceeded")
                return email_record.id, False

            # Create Brevo email object
            brevo_email = self._create_brevo_email(
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

            # Send email via Brevo
            response = self.brevo_api.send_transac_email(brevo_email)

            # Success - Brevo returns message_id in response
            message_id = response.message_id if hasattr(response, 'message_id') else None

            self._update_email_status(
                email_record.id,
                MessageStatus.SENT,
                provider_id=message_id,
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
                {"message_id": message_id}
            )

            log_message_sent(
                message_type="email",
                message_id=email_record.id,
                tenant_id=tenant_id,
                recipient=to_email,
                provider="brevo",
                subject=subject
            )

            return email_record.id, True

        except ApiException as e:
            # Brevo API error
            error_msg = f"Brevo API error: {e.status} - {e.reason}"
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
            # General exception
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

    def _create_brevo_email(
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
    ) -> sib_api_v3_sdk.SendSmtpEmail:
        """Create Brevo SendSmtpEmail object"""

        # Prepare sender
        sender = {"name": from_name, "email": from_email}

        # Prepare recipient(s)
        to = [{"email": to_email}]
        if to_name:
            to[0]["name"] = to_name

        # Create email object
        email_data = {
            "sender": sender,
            "to": to,
            "subject": subject,
        }

        # Add HTML content if provided
        if html_content:
            email_data["html_content"] = html_content

        # Add text content if provided
        if text_content:
            email_data["text_content"] = text_content

        # Add reply-to (same as sender for now)
        email_data["reply_to"] = sender

        # Add attachments if provided
        if attachments:
            brevo_attachments = []
            for attachment_info in attachments:
                try:
                    brevo_attachment = self._create_attachment(attachment_info)
                    if brevo_attachment:
                        brevo_attachments.append(brevo_attachment)
                except Exception as e:
                    self.logger.warning(f"Failed to add attachment: {e}")

            if brevo_attachments:
                email_data["attachment"] = brevo_attachments

        # Note: Brevo doesn't have the same tracking settings API as SendGrid
        # Tracking is typically enabled at the account level in Brevo dashboard
        # If needed, you can add headers for tracking:
        # email_data["headers"] = {"X-Mailin-custom": "tracking_data"}

        return sib_api_v3_sdk.SendSmtpEmail(**email_data)

    def _create_attachment(self, attachment_info: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Create Brevo attachment from attachment info"""

        filename = attachment_info.get("filename")
        content = attachment_info.get("content")  # Base64 encoded content

        if not all([filename, content]):
            return None

        # Brevo expects attachments in this format:
        # {"content": "base64_string", "name": "filename"}
        return {
            "content": content,
            "name": filename
        }

    def _get_tenant_settings(self, tenant_id: str) -> TenantSettings:
        """Get or create tenant settings"""
        settings = self.db.query(TenantSettings).filter(
            TenantSettings.tenant_id == tenant_id
        ).first()

        if not settings:
            # Create default settings
            now = datetime.utcnow()
            settings = TenantSettings(
                tenant_id=tenant_id,
                default_from_email=self.default_from_email,
                default_from_name=self.default_from_name,
                limit_reset_date=now,  # Explicitly set to avoid NOT NULL violation
                created_at=now  # Explicitly set to avoid NOT NULL violation
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
        now = datetime.utcnow()
        log_entry = DeliveryLog(
            message_id=message_id,
            message_type=message_type,
            tenant_id=tenant_id,
            event_type=event_type,
            provider_name="brevo",
            provider_response=provider_response,
            occurred_at=now,
            created_at=now  # Explicitly set to avoid NOT NULL violation
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

    # Webhook handling commented out - not needed for basic email sending
    # TODO: Implement Brevo webhook handling if tracking is needed in the future
    """
    def handle_webhook(self, webhook_data: List[Dict[str, Any]]) -> bool:
        '''Handle Brevo webhook events'''
        try:
            for event in webhook_data:
                event_type = event.get("event")
                brevo_message_id = event.get("message-id")

                if not event_type:
                    continue

                # Find email by provider ID
                email = self.db.query(EmailMessage).filter(
                    EmailMessage.provider_id == brevo_message_id
                ).first()

                if not email:
                    continue

                # Update email status based on event
                # (Implementation depends on Brevo webhook event format)
                pass

            return True

        except Exception as e:
            self.logger.error(f"Failed to process webhook: {e}")
            return False
    """
