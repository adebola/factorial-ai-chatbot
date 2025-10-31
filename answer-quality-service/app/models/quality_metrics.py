"""
RAG Quality Metrics Model

Stores quality metrics for each AI-generated answer.
"""

from sqlalchemy import Column, String, Float, Integer, DateTime, func
from app.core.database import Base


class RAGQualityMetrics(Base):
    """
    Quality metrics for RAG (Retrieval Augmented Generation) responses.

    Tracks:
    - Retrieval quality (how relevant were the documents)
    - Answer confidence (how confident was the LLM)
    - Response characteristics (length, time, sources)
    - Optional basic sentiment (VADER)
    """

    __tablename__ = "rag_quality_metrics"

    id = Column(String(36), primary_key=True, index=True)
    tenant_id = Column(String(36), nullable=False, index=True)
    session_id = Column(String(36), nullable=False, index=True)
    message_id = Column(String(36), nullable=False, index=True, unique=True)  # References chat_messages.id

    # RAG Metrics
    retrieval_score = Column(Float, nullable=True)  # Average relevance of retrieved docs (0-1)
    documents_retrieved = Column(Integer, nullable=True)  # Number of docs used
    answer_confidence = Column(Float, nullable=True)  # LLM confidence score (0-1)
    sources_cited = Column(Integer, nullable=True)  # Number of sources cited in response

    # Answer Characteristics
    answer_length = Column(Integer, nullable=True)  # Character count of AI response
    response_time_ms = Column(Integer, nullable=True)  # Generation time in milliseconds

    # Optional Basic Sentiment (VADER)
    basic_sentiment = Column(String(20), nullable=True)  # 'positive', 'neutral', 'negative', 'frustrated'
    sentiment_confidence = Column(Float, nullable=True)  # VADER compound score

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self):
        return f"<RAGQualityMetrics(id={self.id}, message_id={self.message_id}, confidence={self.answer_confidence})>"
