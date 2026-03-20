import uuid
from sqlalchemy import Column, String, Boolean, Float, Text, DateTime, UniqueConstraint
from sqlalchemy.sql import func

from ..core.database import Base


class ObservabilityBackend(Base):
    """Per-tenant backend configuration for observability data sources."""
    __tablename__ = "observability_backends"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), nullable=False, index=True)
    backend_type = Column(String(50), nullable=False)  # prometheus, alertmanager, elasticsearch, jaeger, kubernetes, otel_collector, llm
    url = Column(String(500), nullable=True)
    auth_type = Column(String(20), nullable=False, default="none")  # none, basic, bearer, service_account
    credentials_encrypted = Column(Text, nullable=True)
    verify_ssl = Column(Boolean, default=True, nullable=False)
    timeout_seconds = Column(Float, default=10.0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "backend_type", name="uq_tenant_backend_type"),
    )
