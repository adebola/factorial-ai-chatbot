from sqlalchemy import Column, String, Text, DateTime, JSON
from sqlalchemy.sql import func
import uuid

from ..core.database import Base


class WorkflowActionData(Base):
    """
    Stores data saved from workflow action steps.
    Allows workflows to persist custom data to the database.
    """
    __tablename__ = "workflow_action_data"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), nullable=False, index=True)
    workflow_id = Column(String(36), nullable=False, index=True)
    execution_id = Column(String(36), nullable=False, index=True)

    # Action metadata
    action_name = Column(String(255), nullable=True)

    # Data payload (flexible JSON storage)
    data = Column(JSON, nullable=False)

    # Audit fields
    created_at = Column(DateTime, default=func.now(), nullable=False)

    def __repr__(self):
        return f"<WorkflowActionData(id={self.id}, workflow_id={self.workflow_id}, execution_id={self.execution_id})>"
