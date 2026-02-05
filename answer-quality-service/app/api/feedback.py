"""
Feedback API Endpoints

Allows users to submit and retrieve feedback on AI responses.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List
from app.schemas.feedback import FeedbackCreate, FeedbackResponse, FeedbackStats
from app.services.feedback_service import FeedbackService
from app.core.database import get_db
from app.core.auth import validate_token, get_tenant_id, validate_api_key
from app.core.logging_config import get_logger, set_request_context
import uuid

logger = get_logger(__name__)

router = APIRouter()


@router.post(
    "/",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit feedback",
    description="Submit thumbs up/down feedback for an AI response"
)
async def submit_feedback(
    feedback: FeedbackCreate,
    claims: dict = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """
    Submit feedback for an AI response.

    Users can provide:
    - **feedback_type**: 'helpful' or 'not_helpful'
    - **comment**: Optional explanation (recommended for negative feedback)

    If feedback already exists for this message, it will be updated.
    """
    tenant_id = get_tenant_id(claims)
    user_id = claims.get("sub")

    # Set request context for logging
    request_id = str(uuid.uuid4())
    set_request_context(
        request_id=request_id,
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=feedback.session_id
    )

    logger.info(
        "Feedback submission request",
        message_id=feedback.message_id,
        feedback_type=feedback.feedback_type
    )

    try:
        service = FeedbackService(db)
        result = await service.submit_feedback(
            tenant_id=tenant_id,
            message_id=feedback.message_id,
            session_id=feedback.session_id,
            feedback_type=feedback.feedback_type,
            comment=feedback.comment
        )

        return result

    except Exception as e:
        logger.exception(f"Error submitting feedback: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit feedback: {str(e)}"
        )


@router.get(
    "/message/{message_id}",
    response_model=FeedbackResponse,
    summary="Get message feedback",
    description="Get feedback for a specific message"
)
async def get_message_feedback(
    message_id: str,
    claims: dict = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """
    Get feedback for a specific message.

    Returns 404 if no feedback exists for this message.
    """
    tenant_id = get_tenant_id(claims)

    service = FeedbackService(db)
    feedback = await service.get_message_feedback(tenant_id, message_id)

    if not feedback:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No feedback found for message {message_id}"
        )

    return feedback


@router.get(
    "/session/{session_id}",
    response_model=List[FeedbackResponse],
    summary="Get session feedback",
    description="Get all feedback for a chat session"
)
async def get_session_feedback(
    session_id: str,
    limit: int = Query(100, le=500, description="Maximum number of feedback records to return"),
    claims: dict = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """
    Get all feedback for a chat session.

    Returns feedback sorted by creation time (most recent first).
    """
    tenant_id = get_tenant_id(claims)

    service = FeedbackService(db)
    feedback_list = await service.get_session_feedback(
        tenant_id=tenant_id,
        session_id=session_id,
        limit=limit
    )

    return feedback_list


@router.get(
    "/stats",
    response_model=FeedbackStats,
    summary="Get feedback statistics",
    description="Get overall feedback statistics for the tenant"
)
async def get_feedback_stats(
    session_id: str = Query(None, description="Optional session ID to filter by"),
    claims: dict = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """
    Get feedback statistics.

    Can be filtered by session_id or return overall tenant statistics.

    Returns:
    - Total feedback count
    - Helpful/not helpful counts
    - Helpful percentage
    - Recent feedback examples
    """
    tenant_id = get_tenant_id(claims)

    service = FeedbackService(db)

    # Get statistics
    stats = await service.get_feedback_stats(
        tenant_id=tenant_id,
        session_id=session_id
    )

    # Get recent feedback (last 5)
    if session_id:
        recent_feedback = await service.get_session_feedback(
            tenant_id=tenant_id,
            session_id=session_id,
            limit=5
        )
    else:
        # Get most recent feedback across all sessions
        from app.models.feedback import AnswerFeedback
        recent_feedback = db.query(AnswerFeedback).filter(
            AnswerFeedback.tenant_id == tenant_id
        ).order_by(
            AnswerFeedback.created_at.desc()
        ).limit(5).all()

    return FeedbackStats(
        total_feedback=stats["total_feedback"],
        helpful_count=stats["helpful_count"],
        not_helpful_count=stats["not_helpful_count"],
        helpful_percentage=stats["helpful_percentage"],
        recent_feedback=recent_feedback
    )


@router.post(
    "/widget/submit",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit feedback from widget",
    description="Submit thumbs up/down feedback from chat widget (API key authentication)"
)
async def submit_widget_feedback(
    feedback: FeedbackCreate,
    tenant_id: str = Depends(validate_api_key),
    db: Session = Depends(get_db)
):
    """
    Submit feedback from chat widget.

    This endpoint uses API key authentication (X-API-Key header) instead of JWT tokens,
    allowing anonymous widget users to provide feedback.

    Users can provide:
    - **feedback_type**: 'helpful' or 'not_helpful'
    - **comment**: Optional explanation (recommended for negative feedback)

    If feedback already exists for this message, it will be updated.
    """
    # Set request context for logging
    request_id = str(uuid.uuid4())
    set_request_context(
        request_id=request_id,
        tenant_id=tenant_id,
        session_id=feedback.session_id
    )

    logger.info(
        "Widget feedback submission",
        message_id=feedback.message_id,
        feedback_type=feedback.feedback_type
    )

    try:
        service = FeedbackService(db)
        result = await service.submit_feedback(
            tenant_id=tenant_id,
            message_id=feedback.message_id,
            session_id=feedback.session_id,
            feedback_type=feedback.feedback_type,
            comment=feedback.comment
        )

        return result

    except Exception as e:
        logger.exception(f"Error submitting widget feedback: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit feedback: {str(e)}"
        )
