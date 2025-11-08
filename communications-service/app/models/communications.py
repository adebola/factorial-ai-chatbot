import enum
import uuid

from sqlalchemy import Column, String, Text, DateTime, Boolean, Integer, JSON, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class MessageStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    BOUNCED = "bounced"
    OPENED = "opened"
    CLICKED = "clicked"


class MessageType(str, enum.Enum):
    EMAIL = "email"
    SMS = "sms"


class TemplateType(str, enum.Enum):
    EMAIL = "email"
    SMS = "sms"


class EmailMessage(Base):
    """Email message records"""
    __tablename__ = "email_messages"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), nullable=False, index=True)

    # Email details
    to_email = Column(String(255), nullable=False)
    to_name = Column(String(255), nullable=True)
    from_email = Column(String(255), nullable=False)
    from_name = Column(String(255), nullable=True)

    subject = Column(String(500), nullable=False)
    html_content = Column(Text, nullable=True)
    text_content = Column(Text, nullable=True)

    # Metadata
    # template_id = Column(String(36), ForeignKey("message_templates.id"), nullable=True)
    # template_data = Column(JSON, nullable=True)  # Data used for template substitution

    # Delivery tracking
    status = Column(String(20), default=MessageStatus.PENDING.value, nullable=False)
    provider_message_id = Column(String(255), nullable=True)  # SendGrid message ID

    # Attachment info (stored as JSON array)
    attachments = Column(JSON, nullable=True)  # [{"filename": "file.pdf", "content_type": "application/pdf", "size": 1024}]

    # Tracking
    sent_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    opened_at = Column(DateTime(timezone=True), nullable=True)
    clicked_at = Column(DateTime(timezone=True), nullable=True)

    # Error handling
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    last_retry_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class SmsMessage(Base):
    """SMS message records"""
    __tablename__ = "sms_messages"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), nullable=False, index=True)

    # SMS details
    to_phone = Column(String(20), nullable=False)
    from_phone = Column(String(20), nullable=False)
    message = Column(Text, nullable=False)

    # # Metadata
    # template_id = Column(String(36), ForeignKey("message_templates.id"), nullable=True)
    # template_data = Column(JSON, nullable=True)

    # Delivery tracking
    status = Column(String(20), default=MessageStatus.PENDING.value, nullable=False)
    provider_message_id = Column(String(255), nullable=True)  # Provider message ID

    # Tracking
    sent_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)

    # Error handling
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    last_retry_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class MessageTemplate(Base):
    """Reusable message templates"""
    __tablename__ = "message_templates"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), nullable=False, index=True)

    # Template details
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    template_type = Column(String(20), nullable=False)

    # Email template fields
    subject_template = Column(String(500), nullable=True)  # For email only
    html_template = Column(Text, nullable=True)
    text_template = Column(Text, nullable=True)

    # SMS template fields (uses text_template)

    # Metadata
    variables = Column(JSON, nullable=True)  # List of template variables: ["name", "company", "amount"]
    is_active = Column(Boolean, default=True)

    # Usage tracking
    usage_count = Column(Integer, default=0)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class DeliveryLog(Base):
    """Detailed delivery and webhook logs"""
    __tablename__ = "delivery_logs"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))

    # Reference to original message
    message_id = Column(String(36), nullable=False, index=True)
    message_type = Column(String(20), nullable=False)
    tenant_id = Column(String(36), nullable=False, index=True)

    # Event details
    event_type = Column(String(50), nullable=False)  # sent, delivered, bounced, opened, clicked, etc.
    event_data = Column(JSON, nullable=True)  # Raw webhook data

    # Provider details
    provider_name = Column(String(50), nullable=False)  # sendgrid, twilio, etc.
    provider_response = Column(JSON, nullable=True)

    # Timestamps
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class TenantSettings(Base):
    """Tenant-specific communication settings"""
    __tablename__ = "tenant_settings"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), nullable=False, unique=True, index=True)

    # Email settings
    default_from_email = Column(String(255), nullable=True)
    default_from_name = Column(String(255), nullable=True)
    email_signature = Column(Text, nullable=True)

    # SMS settings
    default_from_phone = Column(String(20), nullable=True)

    # Rate limiting
    daily_email_limit = Column(Integer, default=1000)
    daily_sms_limit = Column(Integer, default=100)
    emails_sent_today = Column(Integer, default=0)
    sms_sent_today = Column(Integer, default=0)
    limit_reset_date = Column(DateTime(timezone=True), server_default=func.now())

    # Preferences
    enable_open_tracking = Column(Boolean, default=True)
    enable_click_tracking = Column(Boolean, default=True)
    enable_unsubscribe_link = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())