import uuid
from sqlalchemy import Column, String, Text, Float, Integer, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..core.database import Base


class ObservationQuery(Base):
    """Individual observation query with tool execution log."""
    __tablename__ = "observation_queries"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("observation_sessions.id"), nullable=False, index=True)
    tenant_id = Column(String(36), nullable=False, index=True)
    user_message = Column(Text, nullable=False)
    agent_response = Column(Text, nullable=True)
    tool_calls = Column(JSON, nullable=True)  # [{tool, input, output, duration_ms}]
    total_duration_ms = Column(Float, nullable=True)
    llm_tokens_used = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False, default="completed")  # completed, error, timeout
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("ObservationSession", back_populates="queries")
