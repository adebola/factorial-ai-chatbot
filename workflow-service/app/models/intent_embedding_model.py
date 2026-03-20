import uuid
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector

from ..core.database import Base


class WorkflowIntentEmbedding(Base):
    """Stores pre-computed intent pattern embeddings for pgvector similarity search."""
    __tablename__ = "workflow_intent_embeddings"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), nullable=False, index=True)
    workflow_id = Column(String(36), ForeignKey("workflows.id", ondelete="SET NULL"), nullable=True)
    pattern_text = Column(Text, nullable=False)
    embedding = Column(Vector(1536), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<WorkflowIntentEmbedding(id={self.id}, workflow_id={self.workflow_id})>"
