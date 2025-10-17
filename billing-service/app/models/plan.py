import uuid
from sqlalchemy import Column, String, Integer, DateTime, Boolean, Text, JSON, Numeric
from sqlalchemy.sql import func

from ..core.database import Base


class Plan(Base):
    """Subscription plans (Basic, Lite, Pro, Enterprise)"""
    __tablename__ = "plans"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)

    # Usage Limits (-1 = unlimited)
    document_limit = Column(Integer, nullable=False, default=10)
    website_limit = Column(Integer, nullable=False, default=1)
    daily_chat_limit = Column(Integer, nullable=False, default=50)
    monthly_chat_limit = Column(Integer, nullable=False, default=1500)

    # New Limits
    max_document_size_mb = Column(Integer, nullable=False, default=2)  # Max document size in MB
    max_pages_per_website = Column(Integer, nullable=True)  # NULL = unlimited pages

    # Pricing (NGN)
    monthly_plan_cost = Column(Numeric(10, 2), nullable=False, default=0.00)
    yearly_plan_cost = Column(Numeric(10, 2), nullable=False, default=0.00)

    # Trial Period
    has_trial = Column(Boolean, default=False, nullable=False)
    trial_days = Column(Integer, default=0, nullable=False)

    # Feature Flags
    has_sentiment_analysis = Column(Boolean, default=False, nullable=False)
    has_conversational_workflow = Column(Boolean, default=False, nullable=False)
    has_api_access = Column(Boolean, default=False, nullable=False)
    has_custom_integrations = Column(Boolean, default=False, nullable=False)
    has_on_premise = Column(Boolean, default=False, nullable=False)

    # Analytics Level
    analytics_level = Column(String(20), default="basic", nullable=False)  # "basic", "full"

    # Support Channels
    support_channels = Column(JSON, default=["email"])  # ["email", "phone", "dedicated"]

    # Features (structured JSON for additional features)
    features = Column(JSON, default={})

    # Soft deletion
    is_active = Column(Boolean, default=True, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
