"""
Pydantic schemas for feedback API.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class FeedbackCreate(BaseModel):
    """Request schema for creating feedback"""
    message_id: str = Field(..., description="ID of the AI message being rated")
    session_id: str = Field(..., description="Chat session ID")
    feedback_type: str = Field(..., description="'helpful' or 'not_helpful'", pattern="^(helpful|not_helpful)$")
    comment: Optional[str] = Field(None, description="Optional user comment explaining the feedback")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "message_id": "msg-123e4567-e89b-12d3-a456-426614174000",
                    "session_id": "session-123e4567-e89b-12d3-a456-426614174000",
                    "feedback_type": "helpful",
                    "comment": "This answer was very clear and helpful!"
                }
            ]
        }
    }


class FeedbackResponse(BaseModel):
    """Response schema for feedback"""
    id: str
    tenant_id: str
    session_id: str
    message_id: str
    feedback_type: str
    feedback_comment: Optional[str]
    created_at: datetime

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "examples": [
                {
                    "id": "fb-123e4567-e89b-12d3-a456-426614174000",
                    "tenant_id": "tenant-123e4567-e89b-12d3-a456-426614174000",
                    "session_id": "session-123e4567-e89b-12d3-a456-426614174000",
                    "message_id": "msg-123e4567-e89b-12d3-a456-426614174000",
                    "feedback_type": "helpful",
                    "feedback_comment": "This answer was very clear and helpful!",
                    "created_at": "2025-01-17T10:30:00Z"
                }
            ]
        }
    }


class FeedbackStats(BaseModel):
    """Feedback statistics for a session or tenant"""
    total_feedback: int
    helpful_count: int
    not_helpful_count: int
    helpful_percentage: float
    recent_feedback: list[FeedbackResponse]

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "total_feedback": 25,
                    "helpful_count": 20,
                    "not_helpful_count": 5,
                    "helpful_percentage": 0.8,
                    "recent_feedback": []
                }
            ]
        }
    }
