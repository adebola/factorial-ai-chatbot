"""
Session Quality Model

Stores aggregated quality metrics for entire chat sessions.
"""

from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, func
from sqlalchemy.dialects.postgresql import JSON
from app.core.database import Base


class SessionQuality(Base):
    """
    Session-level quality summary.

    Aggregates quality metrics, feedback, and success indicators
    for an entire chat session.
    """

    __tablename__ = "session_quality"

    id = Column(String(36), primary_key=True, index=True)
    tenant_id = Column(String(36), nullable=False, index=True)
    session_id = Column(String(36), nullable=False, index=True, unique=True)  # References chat_sessions.id

    # Overall Metrics
    total_messages = Column(Integer, default=0, nullable=False)
    messages_with_feedback = Column(Integer, default=0, nullable=False)
    helpful_count = Column(Integer, default=0, nullable=False)
    not_helpful_count = Column(Integer, default=0, nullable=False)

    # Quality Scores
    avg_retrieval_score = Column(Float, nullable=True)
    avg_confidence_score = Column(Float, nullable=True)
    avg_response_time_ms = Column(Integer, nullable=True)

    # Session Outcome
    session_success = Column(Boolean, nullable=True)  # Did user achieve their goal?
    success_indicators = Column(JSON, nullable=True)  # {"resolved": true, "feedback": "positive"}

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<SessionQuality(id={self.id}, session_id={self.session_id}, success={self.session_success})>"
