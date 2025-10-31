"""
Pydantic schemas for quality metrics.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class QualityMetricsCreate(BaseModel):
    """Request schema for creating quality metrics"""
    message_id: str = Field(..., description="ID of the AI message")
    session_id: str = Field(..., description="Chat session ID")

    # RAG Metrics
    retrieval_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Average relevance of retrieved docs (0-1)")
    documents_retrieved: Optional[int] = Field(None, ge=0, description="Number of documents used")
    answer_confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="LLM confidence score (0-1)")
    sources_cited: Optional[int] = Field(None, ge=0, description="Number of sources cited")

    # Answer Characteristics
    answer_length: Optional[int] = Field(None, ge=0, description="Character count of AI response")
    response_time_ms: Optional[int] = Field(None, ge=0, description="Generation time in milliseconds")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "message_id": "msg-123e4567-e89b-12d3-a456-426614174000",
                    "session_id": "session-123e4567-e89b-12d3-a456-426614174000",
                    "retrieval_score": 0.85,
                    "documents_retrieved": 5,
                    "answer_confidence": 0.78,
                    "sources_cited": 3,
                    "answer_length": 450,
                    "response_time_ms": 1250
                }
            ]
        }
    }


class QualityMetricsResponse(BaseModel):
    """Response schema for quality metrics"""
    id: str
    tenant_id: str
    session_id: str
    message_id: str

    # RAG Metrics
    retrieval_score: Optional[float]
    documents_retrieved: Optional[int]
    answer_confidence: Optional[float]
    sources_cited: Optional[int]

    # Answer Characteristics
    answer_length: Optional[int]
    response_time_ms: Optional[int]

    # Sentiment (if enabled)
    basic_sentiment: Optional[str]
    sentiment_confidence: Optional[float]

    created_at: datetime

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "examples": [
                {
                    "id": "qm-123e4567-e89b-12d3-a456-426614174000",
                    "tenant_id": "tenant-123e4567-e89b-12d3-a456-426614174000",
                    "session_id": "session-123e4567-e89b-12d3-a456-426614174000",
                    "message_id": "msg-123e4567-e89b-12d3-a456-426614174000",
                    "retrieval_score": 0.85,
                    "documents_retrieved": 5,
                    "answer_confidence": 0.78,
                    "sources_cited": 3,
                    "answer_length": 450,
                    "response_time_ms": 1250,
                    "basic_sentiment": "neutral",
                    "sentiment_confidence": 0.12,
                    "created_at": "2025-01-17T10:30:00Z"
                }
            ]
        }
    }


class ChatMessageEvent(BaseModel):
    """Schema for chat.message.created RabbitMQ event"""
    event_type: str
    tenant_id: str
    session_id: str
    message_id: str
    message_type: str  # 'user' or 'assistant'
    content_preview: Optional[str] = None  # First 200 chars for sentiment analysis

    quality_metrics: Optional[dict] = None  # Optional quality metrics from chat service

    timestamp: str

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "event_type": "message.created",
                    "tenant_id": "tenant-123",
                    "session_id": "session-456",
                    "message_id": "msg-789",
                    "message_type": "assistant",
                    "content_preview": "Based on the documents, here's what I found...",
                    "quality_metrics": {
                        "retrieval_score": 0.85,
                        "documents_retrieved": 5,
                        "answer_confidence": 0.78,
                        "sources_cited": 3,
                        "answer_length": 450,
                        "response_time_ms": 1250
                    },
                    "timestamp": "2025-01-17T10:30:00Z"
                }
            ]
        }
    }


class QualityStats(BaseModel):
    """Quality statistics for a session or tenant"""
    total_messages: int
    avg_retrieval_score: Optional[float]
    avg_confidence_score: Optional[float]
    avg_response_time_ms: Optional[int]
    low_confidence_count: int  # Messages with confidence < 0.5
    sentiment_breakdown: dict  # {"positive": 10, "neutral": 50, "negative": 5}

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "total_messages": 100,
                    "avg_retrieval_score": 0.72,
                    "avg_confidence_score": 0.68,
                    "avg_response_time_ms": 1350,
                    "low_confidence_count": 12,
                    "sentiment_breakdown": {
                        "positive": 15,
                        "neutral": 70,
                        "negative": 10,
                        "frustrated": 5
                    }
                }
            ]
        }
    }
