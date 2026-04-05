"""Immutable audit event model. No UPDATE or DELETE operations permitted."""
import uuid
from sqlalchemy import Column, String, Integer, DateTime, JSON, Text, Index
from sqlalchemy.sql import func

from ..core.database import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("idx_audit_tenant_time", "tenant_id", "created_at"),
        Index("idx_audit_user_time", "actor_user_id", "created_at"),
        Index("idx_audit_action_time", "action_type", "created_at"),
        Index("idx_audit_trace", "trace_id"),
        Index("idx_audit_resource", "resource_type", "resource_id"),
    )

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    event_id = Column(String(36), unique=True, nullable=False)

    # Who
    tenant_id = Column(String(36), nullable=False)
    actor_user_id = Column(String(36), nullable=True)
    actor_email = Column(String(255), nullable=True)
    actor_type = Column(String(20), nullable=False)  # user | system | scheduler

    # What
    action_type = Column(String(100), nullable=False)  # e.g. document.uploaded, login.success
    tier = Column(String(20), nullable=False)          # security | data
    resource_type = Column(String(50), nullable=True)
    resource_id = Column(String(36), nullable=True)

    # Where
    source_service = Column(String(50), nullable=False)
    trace_id = Column(String(32), nullable=True)
    span_id = Column(String(16), nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)

    # State change
    before_state = Column(JSON, nullable=True)
    after_state = Column(JSON, nullable=True)
    event_metadata = Column(JSON, nullable=True)

    # Timestamps
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Retention
    retention_days = Column(Integer, nullable=True)
