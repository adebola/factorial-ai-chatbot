"""
Knowledge Gap Model

Stores detected knowledge gaps (recurring questions with low-quality answers).
"""

from sqlalchemy import Column, String, Text, Integer, Float, DateTime, func
from sqlalchemy.dialects.postgresql import JSON
from app.core.database import Base


class KnowledgeGap(Base):
    """
    Detected knowledge gaps in the RAG system.

    A knowledge gap is identified when:
    - Multiple similar questions are asked
    - Answers have low confidence scores
    - Users provide negative feedback
    """

    __tablename__ = "knowledge_gaps"

    id = Column(String(36), primary_key=True, index=True)
    tenant_id = Column(String(36), nullable=False, index=True)

    # Gap Information
    question_pattern = Column(Text, nullable=False)  # Generalized question pattern
    example_questions = Column(JSON, nullable=False)  # Array of actual user questions
    occurrence_count = Column(Integer, default=1, nullable=False)  # How many times asked

    # Quality Indicators
    avg_confidence = Column(Float, nullable=True)  # Average confidence of answers
    negative_feedback_count = Column(Integer, default=0, nullable=False)  # Thumbs down count

    # Gap Status
    status = Column(String(20), default="detected", nullable=False)  # 'detected', 'acknowledged', 'resolved'
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolution_notes = Column(Text, nullable=True)

    first_detected_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_occurrence_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self):
        return f"<KnowledgeGap(id={self.id}, pattern={self.question_pattern[:50]}, status={self.status})>"
