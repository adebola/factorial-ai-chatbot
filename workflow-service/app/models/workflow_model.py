from sqlalchemy import Column, String, Text, Boolean, DateTime, Integer, JSON, Enum as SQLEnum
from sqlalchemy.sql import func
import uuid
import enum
from datetime import datetime

from ..core.database import Base


class WorkflowStatus(enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class TriggerType(enum.Enum):
    MESSAGE = "message"
    INTENT = "intent"
    KEYWORD = "keyword"
    MANUAL = "manual"


class Workflow(Base):
    """Workflow definitions with tenant isolation"""
    __tablename__ = "workflows"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), nullable=False, index=True)

    # Basic workflow info
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    version = Column(String(50), default="1.0.0")
    status = Column(String(20), default=WorkflowStatus.DRAFT.value, nullable=False)

    # Workflow definition (YAML/JSON)
    definition = Column(JSON, nullable=False)

    # Trigger configuration
    trigger_type = Column(String(20), nullable=False)
    trigger_config = Column(JSON, nullable=True)  # Trigger conditions, keywords, etc.

    # Workflow metadata
    is_active = Column(Boolean, default=False)
    usage_count = Column(Integer, default=0)
    last_used_at = Column(DateTime, nullable=True)

    # Audit fields
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    created_by = Column(String(36), nullable=True)  # User ID
    updated_by = Column(String(36), nullable=True)  # User ID

    def __repr__(self):
        return f"<Workflow(id={self.id}, name={self.name}, tenant_id={self.tenant_id})>"


class WorkflowVersion(Base):
    """Version history for workflows"""
    __tablename__ = "workflow_versions"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    workflow_id = Column(String(36), nullable=False, index=True)
    tenant_id = Column(String(36), nullable=False, index=True)

    version = Column(String(50), nullable=False)
    definition = Column(JSON, nullable=False)
    change_summary = Column(Text, nullable=True)

    created_at = Column(DateTime, default=func.now(), nullable=False)
    created_by = Column(String(36), nullable=True)

    def __repr__(self):
        return f"<WorkflowVersion(workflow_id={self.workflow_id}, version={self.version})>"


class WorkflowTemplate(Base):
    """Reusable workflow templates"""
    __tablename__ = "workflow_templates"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))

    # Template info
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=True)  # lead_qualification, support, onboarding
    tags = Column(JSON, nullable=True)  # Array of tags

    # Template definition
    definition = Column(JSON, nullable=False)
    default_config = Column(JSON, nullable=True)  # Default configuration options

    # Template metadata
    is_public = Column(Boolean, default=False)  # Public templates available to all tenants
    usage_count = Column(Integer, default=0)
    rating = Column(Integer, default=0)  # Average rating 1-5

    # Audit fields
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    created_by = Column(String(36), nullable=True)

    def __repr__(self):
        return f"<WorkflowTemplate(id={self.id}, name={self.name})>"