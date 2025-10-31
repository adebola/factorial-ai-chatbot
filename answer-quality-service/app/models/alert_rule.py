"""
Alert Rule Model

Defines configurable alert rules for quality monitoring.
"""

from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, func
from sqlalchemy.dialects.postgresql import JSON
from app.core.database import Base


class AlertRule(Base):
    """
    Configurable alert rules for quality monitoring.

    Alert types:
    - quality_drop: Avg confidence below threshold
    - new_gaps: New knowledge gaps detected
    - high_negative_feedback: Negative feedback rate above threshold
    - session_degradation: Session quality drops significantly
    """

    __tablename__ = "alert_rules"

    id = Column(String(36), primary_key=True, index=True)
    tenant_id = Column(String(36), nullable=False, index=True)

    # Rule Configuration
    name = Column(String(255), nullable=False)
    rule_type = Column(String(50), nullable=False)  # quality_drop, new_gaps, high_negative_feedback, session_degradation
    description = Column(String(500), nullable=True)

    # Threshold Configuration
    threshold_value = Column(Float, nullable=False)  # e.g., 0.5 for confidence, 0.3 for negative feedback rate
    check_interval_hours = Column(Integer, default=24, nullable=False)  # How many hours to look back
    min_sample_size = Column(Integer, default=10, nullable=False)  # Minimum messages to trigger alert

    # Notification Configuration
    notification_channels = Column(JSON, nullable=False)  # ["email", "webhook"]
    notification_recipients = Column(JSON, nullable=True)  # Email addresses or webhook URLs

    # Throttling
    throttle_minutes = Column(Integer, default=1440, nullable=False)  # Default: 24 hours
    last_triggered_at = Column(DateTime(timezone=True), nullable=True)

    # Status
    enabled = Column(Boolean, default=True, nullable=False)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by = Column(String(36), nullable=True)  # User ID who created the rule

    def __repr__(self):
        return f"<AlertRule(id={self.id}, name={self.name}, type={self.rule_type}, enabled={self.enabled})>"
