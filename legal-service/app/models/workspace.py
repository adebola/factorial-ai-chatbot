import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey, Index
from ..core.database import Base


class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    workspace_type = Column(String(50), nullable=False, default="project")  # project | shared_corpus
    status = Column(String(20), nullable=False, default="active")  # active | archived
    created_by = Column(String(36), nullable=True)
    created_by_email = Column(String(255), nullable=True)
    is_archived = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=lambda: datetime.now(timezone.utc))


class WorkspaceDocument(Base):
    __tablename__ = "workspace_documents"
    __table_args__ = (
        Index("idx_wd_workspace_id", "workspace_id"),
        Index("idx_wd_document_id", "document_id"),
    )

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False)
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=False)
    added_by = Column(String(36), nullable=True)
    added_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    removed_at = Column(DateTime(timezone=True), nullable=True)  # null = active membership
    removed_by = Column(String(36), nullable=True)
