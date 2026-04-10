"""Models for the Agentic Service Registry and Tenant Assignment."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Text, Boolean, DateTime, JSON,
    UniqueConstraint, ForeignKey, Index
)
from ..core.database import Base


class AgenticService(Base):
    """Service catalog for custom agentic services."""
    __tablename__ = "agentic_services"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), unique=True, nullable=False)
    service_key = Column(String(50), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    base_url = Column(String(500), nullable=True)
    health_check_url = Column(String(500), nullable=True)
    category = Column(String(50), nullable=False, default="agentic")
    icon_url = Column(String(500), nullable=True)
    capabilities = Column(JSON, nullable=True)
    # In-chat widget presentation hints (icon, branding, welcome text). Forwarded
    # to the chat widget by the agent gateway. Distinct from ui_extensions below.
    ui_hints = Column(JSON, nullable=True)
    # Plugin manifest fields — see plan/dreamy-zooming-pizza.md §1-§2.
    # `manifest` holds the entire most-recent manifest fetched from the plugin's
    # GET /manifest endpoint (opaque to the core). `ui_extensions` is the
    # denormalized list of admin-UI menu entries the plugin contributes; the
    # superadmin shell reads this via GET /api/v1/admin/services/ui-extensions.
    manifest = Column(JSON, nullable=True)
    ui_extensions = Column(JSON, nullable=True)
    health_status = Column(String(20), nullable=False, default="unknown")
    last_manifest_fetch_at = Column(DateTime(timezone=True), nullable=True)
    last_health_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    is_deleted = Column(Boolean, nullable=False, default=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=lambda: datetime.now(timezone.utc))


class TenantServiceAssignment(Base):
    """Per-tenant assignment of agentic services."""
    __tablename__ = "tenant_service_assignments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "service_id", name="uq_tenant_service"),
        Index("idx_tsa_tenant_id", "tenant_id"),
        Index("idx_tsa_service_id", "service_id"),
    )

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), nullable=False)
    service_id = Column(String(36), ForeignKey("agentic_services.id"), nullable=False)
    assigned_by = Column(String(36), nullable=False)
    assigned_by_email = Column(String(255), nullable=True)
    config = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    deactivated_at = Column(DateTime(timezone=True), nullable=True)
    deactivated_by = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=lambda: datetime.now(timezone.utc))
