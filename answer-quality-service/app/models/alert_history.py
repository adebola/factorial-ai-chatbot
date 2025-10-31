"""
Alert History Model

Records all triggered alerts for auditing and analysis.
"""

from sqlalchemy import Column, String, Text, DateTime, Boolean, func
from sqlalchemy.dialects.postgresql import JSON
from app.core.database import Base


class AlertHistory(Base):
    """
    Historical record of triggered alerts.

    Tracks when alerts fire, what triggered them, and notification status.
    """

    __tablename__ = "alert_history"

    id = Column(String(36), primary_key=True, index=True)
    tenant_id = Column(String(36), nullable=False, index=True)

    # Alert Rule Reference
    rule_id = Column(String(36), nullable=False, index=True)
    rule_name = Column(String(255), nullable=False)
    rule_type = Column(String(50), nullable=False)

    # Alert Details
    severity = Column(String(20), default="warning", nullable=False)  # info, warning, critical
    alert_message = Column(Text, nullable=False)
    alert_data = Column(JSON, nullable=True)  # Context data (metrics, counts, etc.)

    # Notification Status
    notification_sent = Column(Boolean, default=False, nullable=False)
    notification_channels_used = Column(JSON, nullable=True)  # Which channels were used
    notification_response = Column(JSON, nullable=True)  # Response from notification services
    notification_error = Column(Text, nullable=True)

    # Timestamps
    triggered_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<AlertHistory(id={self.id}, rule={self.rule_name}, severity={self.severity}, sent={self.notification_sent})>"
