import os
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime
from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from ..models.communications import SmsMessage, MessageStatus, DeliveryLog, MessageType, TenantSettings
from ..core.logging_config import get_logger, log_message_sent, log_message_failed


class SMSProvider(ABC):
    """Abstract base class for SMS providers"""

    @abstractmethod
    def send_sms(self, to_phone: str, from_phone: str, message: str, **kwargs) -> Tuple[str, bool, Optional[str]]:
        """
        Send SMS message

        Returns:
            Tuple of (provider_message_id, success, error_message)
        """
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Get provider name"""
        pass


class TwilioProvider(SMSProvider):
    """Twilio SMS provider implementation"""

    def __init__(self):
        self.account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
        self.auth_token = os.environ.get("TWILIO_AUTH_TOKEN")

        if not all([self.account_sid, self.auth_token]):
            raise ValueError("TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN environment variables must be set")

        try:
            from twilio.rest import Client
            self.client = Client(self.account_sid, self.auth_token)
        except ImportError:
            raise ImportError("twilio package is required for Twilio SMS support. Install with: pip install twilio")

    def send_sms(self, to_phone: str, from_phone: str, message: str, **kwargs) -> Tuple[str, bool, Optional[str]]:
        """Send SMS via Twilio"""
        try:
            message_obj = self.client.messages.create(
                body=message,
                from_=from_phone,
                to=to_phone
            )

            return message_obj.sid, True, None

        except Exception as e:
            return None, False, str(e)

    def get_provider_name(self) -> str:
        return "twilio"


class MockSMSProvider(SMSProvider):
    """Mock SMS provider for testing and development"""

    def send_sms(self, to_phone: str, from_phone: str, message: str, **kwargs) -> Tuple[str, bool, Optional[str]]:
        """Mock SMS sending (always succeeds)"""
        import uuid
        mock_id = str(uuid.uuid4())
        print(f"MOCK SMS: From {from_phone} to {to_phone}: {message}")
        return mock_id, True, None

    def get_provider_name(self) -> str:
        return "mock"


class SMSService:
    """Service for sending SMS messages"""

    def __init__(self, db: Session):
        self.db = db
        self.logger = get_logger("sms_service")

        # Initialize SMS provider based on configuration
        self.provider = self._initialize_provider()
        self.default_from_phone = os.environ.get("SMS_FROM_PHONE", "+1234567890")

    def _initialize_provider(self) -> SMSProvider:
        """Initialize SMS provider based on configuration"""
        provider_name = os.environ.get("SMS_PROVIDER", "mock").lower()

        if provider_name == "twilio":
            return TwilioProvider()
        elif provider_name == "mock":
            return MockSMSProvider()
        else:
            raise ValueError(f"Unsupported SMS provider: {provider_name}")

    def send_sms(
        self,
        tenant_id: str,
        to_phone: str,
        message: str,
        from_phone: Optional[str] = None,
        template_id: Optional[str] = None,
        template_data: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, bool]:
        """
        Send an SMS message

        Returns:
            Tuple of (message_id, success)
        """

        # Get tenant settings for defaults
        tenant_settings = self._get_tenant_settings(tenant_id)

        # Use tenant default if not provided
        if not from_phone:
            from_phone = tenant_settings.default_from_phone or self.default_from_phone

        # Create SMS record in database
        sms_record = SmsMessage(
            tenant_id=tenant_id,
            to_phone=to_phone,
            from_phone=from_phone,
            message=message,
            # Note: template_id and template_data removed - fields don't exist in model
            status=MessageStatus.PENDING,
            created_at=datetime.utcnow()  # Explicitly set to avoid NOT NULL violation
        )

        self.db.add(sms_record)
        self.db.commit()
        self.db.refresh(sms_record)

        try:
            # Check rate limits
            if not self._check_rate_limit(tenant_id, tenant_settings):
                self._update_sms_status(sms_record.id, MessageStatus.FAILED, "Rate limit exceeded")
                return sms_record.id, False

            # Send SMS via provider
            provider_id, success, error_message = self.provider.send_sms(
                to_phone=to_phone,
                from_phone=from_phone,
                message=message
            )

            if success:
                # Success
                self._update_sms_status(
                    sms_record.id,
                    MessageStatus.SENT,
                    provider_id=provider_id,
                    sent_at=datetime.utcnow()
                )

                # Update rate limit counter
                self._increment_rate_limit_counter(tenant_id, tenant_settings)

                # Log delivery
                self._log_delivery(
                    sms_record.id,
                    MessageType.SMS,
                    tenant_id,
                    "sent",
                    {"provider_id": provider_id}
                )

                log_message_sent(
                    message_type="sms",
                    message_id=sms_record.id,
                    tenant_id=tenant_id,
                    recipient=to_phone,
                    provider=self.provider.get_provider_name(),
                    message_length=len(message)
                )

                return sms_record.id, True

            else:
                # Failed
                self._update_sms_status(sms_record.id, MessageStatus.FAILED, error_message)

                log_message_failed(
                    message_type="sms",
                    message_id=sms_record.id,
                    tenant_id=tenant_id,
                    recipient=to_phone,
                    error=error_message or "Unknown SMS provider error"
                )

                return sms_record.id, False

        except Exception as e:
            # Exception occurred
            error_msg = f"Failed to send SMS: {str(e)}"
            self._update_sms_status(sms_record.id, MessageStatus.FAILED, error_msg)

            log_message_failed(
                message_type="sms",
                message_id=sms_record.id,
                tenant_id=tenant_id,
                recipient=to_phone,
                error=error_msg
            )

            return sms_record.id, False

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
                default_from_phone=self.default_from_phone,
                limit_reset_date=now,  # Explicitly set to avoid NOT NULL violation
                created_at=now  # Explicitly set to avoid NOT NULL violation
            )
            self.db.add(settings)
            self.db.commit()
            self.db.refresh(settings)

        return settings

    def _check_rate_limit(self, tenant_id: str, tenant_settings: TenantSettings) -> bool:
        """Check if tenant has exceeded daily SMS limit"""
        # Reset counter if it's a new day
        today = datetime.utcnow().date()
        if tenant_settings.limit_reset_date.date() < today:
            tenant_settings.sms_sent_today = 0
            tenant_settings.limit_reset_date = datetime.utcnow()
            self.db.commit()

        return tenant_settings.sms_sent_today < tenant_settings.daily_sms_limit

    def _increment_rate_limit_counter(self, tenant_id: str, tenant_settings: TenantSettings):
        """Increment the daily SMS counter"""
        tenant_settings.sms_sent_today += 1
        self.db.commit()

    def _update_sms_status(
        self,
        sms_id: str,
        status: MessageStatus,
        error_message: Optional[str] = None,
        provider_id: Optional[str] = None,
        sent_at: Optional[datetime] = None,
        delivered_at: Optional[datetime] = None
    ):
        """Update SMS status in database"""
        sms = self.db.query(SmsMessage).filter(SmsMessage.id == sms_id).first()
        if sms:
            sms.status = status
            if error_message:
                sms.error_message = error_message
            if provider_id:
                sms.provider_id = provider_id
            if sent_at:
                sms.sent_at = sent_at
            if delivered_at:
                sms.delivered_at = delivered_at

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
            provider_name=self.provider.get_provider_name(),
            provider_response=provider_response,
            occurred_at=now,
            created_at=now  # Explicitly set to avoid NOT NULL violation
        )

        self.db.add(log_entry)
        self.db.commit()

    def get_sms_status(self, sms_id: str, tenant_id: str) -> Optional[SmsMessage]:
        """Get SMS status for a specific tenant"""
        return self.db.query(SmsMessage).filter(
            SmsMessage.id == sms_id,
            SmsMessage.tenant_id == tenant_id
        ).first()

    def get_tenant_sms(
        self,
        tenant_id: str,
        skip: int = 0,
        limit: int = 50,
        status: Optional[MessageStatus] = None
    ) -> List[SmsMessage]:
        """Get SMS messages for a tenant with pagination"""
        query = self.db.query(SmsMessage).filter(SmsMessage.tenant_id == tenant_id)

        if status:
            query = query.filter(SmsMessage.status == status)

        return query.order_by(SmsMessage.created_at.desc()).offset(skip).limit(limit).all()

    def handle_webhook(self, webhook_data: Dict[str, Any]) -> bool:
        """Handle SMS provider webhook events"""
        try:
            # This will be provider-specific implementation
            # For now, just log the webhook
            self.logger.info(f"SMS webhook received: {webhook_data}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to process SMS webhook: {e}")
            return False