"""
Feedback Service

Handles feedback submission, storage, and event publishing.
"""

import asyncio
import uuid
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, case
from app.models.feedback import AnswerFeedback
from app.models.session_quality import SessionQuality
from app.services.event_publisher import event_publisher
from app.core.logging_config import get_logger, log_feedback_submission

logger = get_logger(__name__)


class FeedbackService:
    """Service for managing answer feedback"""

    def __init__(self, db: Session):
        self.db = db

    async def submit_feedback(
        self,
        tenant_id: str,
        message_id: str,
        session_id: str,
        feedback_type: str,
        comment: Optional[str] = None
    ) -> AnswerFeedback:
        """
        Submit user feedback for an AI response.

        Creates feedback record, publishes event, and updates session quality.

        Args:
            tenant_id: Tenant ID
            message_id: Message ID being rated
            session_id: Chat session ID
            feedback_type: 'helpful' or 'not_helpful'
            comment: Optional user comment

        Returns:
            Created feedback record
        """
        # Check if feedback already exists for this message
        existing_feedback = self.db.query(AnswerFeedback).filter(
            AnswerFeedback.tenant_id == tenant_id,
            AnswerFeedback.message_id == message_id
        ).first()

        if existing_feedback:
            # Update existing feedback
            existing_feedback.feedback_type = feedback_type
            existing_feedback.feedback_comment = comment
            self.db.commit()
            self.db.refresh(existing_feedback)

            logger.info(
                "Updated existing feedback",
                tenant_id=tenant_id,
                message_id=message_id,
                feedback_type=feedback_type
            )

            feedback = existing_feedback
        else:
            # Create new feedback record
            feedback = AnswerFeedback(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                session_id=session_id,
                message_id=message_id,
                feedback_type=feedback_type,
                feedback_comment=comment
            )

            self.db.add(feedback)
            self.db.commit()
            self.db.refresh(feedback)

            logger.info(
                "Created new feedback",
                tenant_id=tenant_id,
                message_id=message_id,
                feedback_type=feedback_type
            )

        # Log feedback submission
        log_feedback_submission(
            tenant_id=tenant_id,
            message_id=message_id,
            feedback_type=feedback_type,
            has_comment=comment is not None
        )

        # Update session quality metrics
        await self._update_session_quality(tenant_id, session_id)

        # Publish feedback event to RabbitMQ
        try:
            asyncio.create_task(event_publisher.publish_feedback_submitted(
                tenant_id=tenant_id,
                session_id=session_id,
                message_id=message_id,
                feedback_type=feedback_type,
                has_comment=comment is not None
            ))
        except Exception as e:
            logger.exception(f"Failed to publish feedback event: {e}")
            # Don't fail the request if event publishing fails

        # TODO: If negative feedback, trigger knowledge gap analysis
        # if feedback_type == "not_helpful":
        #     await self._analyze_for_knowledge_gaps(tenant_id, message_id, session_id)

        return feedback

    async def get_message_feedback(
        self,
        tenant_id: str,
        message_id: str
    ) -> Optional[AnswerFeedback]:
        """
        Get feedback for a specific message.

        Args:
            tenant_id: Tenant ID
            message_id: Message ID

        Returns:
            Feedback record or None if not found
        """
        return self.db.query(AnswerFeedback).filter(
            AnswerFeedback.tenant_id == tenant_id,
            AnswerFeedback.message_id == message_id
        ).first()

    async def get_session_feedback(
        self,
        tenant_id: str,
        session_id: str,
        limit: int = 100
    ) -> list[AnswerFeedback]:
        """
        Get all feedback for a chat session.

        Args:
            tenant_id: Tenant ID
            session_id: Session ID
            limit: Maximum number of feedback records to return

        Returns:
            List of feedback records
        """
        return self.db.query(AnswerFeedback).filter(
            AnswerFeedback.tenant_id == tenant_id,
            AnswerFeedback.session_id == session_id
        ).order_by(
            AnswerFeedback.created_at.desc()
        ).limit(limit).all()

    async def get_feedback_stats(
        self,
        tenant_id: str,
        session_id: Optional[str] = None
    ) -> dict:
        """
        Get feedback statistics for a tenant or session.

        Args:
            tenant_id: Tenant ID
            session_id: Optional session ID to filter by

        Returns:
            Dictionary with feedback statistics
        """
        query = self.db.query(
            func.count(AnswerFeedback.id).label('total'),
            func.sum(
                case((AnswerFeedback.feedback_type == 'helpful', 1), else_=0)
            ).label('helpful'),
            func.sum(
                case((AnswerFeedback.feedback_type == 'not_helpful', 1), else_=0)
            ).label('not_helpful')
        ).filter(
            AnswerFeedback.tenant_id == tenant_id
        )

        if session_id:
            query = query.filter(AnswerFeedback.session_id == session_id)

        result = query.first()

        total = result.total or 0
        helpful = result.helpful or 0
        not_helpful = result.not_helpful or 0
        helpful_percentage = (helpful / total) if total > 0 else 0.0

        return {
            "total_feedback": total,
            "helpful_count": helpful,
            "not_helpful_count": not_helpful,
            "helpful_percentage": round(helpful_percentage, 2)
        }

    async def _update_session_quality(self, tenant_id: str, session_id: str):
        """
        Update session-level quality metrics after feedback submission.

        Args:
            tenant_id: Tenant ID
            session_id: Session ID
        """
        # Get feedback counts for this session
        stats = await self.get_feedback_stats(tenant_id, session_id)

        # Find or create session quality record
        session_quality = self.db.query(SessionQuality).filter(
            SessionQuality.tenant_id == tenant_id,
            SessionQuality.session_id == session_id
        ).first()

        if not session_quality:
            session_quality = SessionQuality(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                session_id=session_id
            )
            self.db.add(session_quality)

        # Update feedback metrics
        session_quality.helpful_count = stats["helpful_count"]
        session_quality.not_helpful_count = stats["not_helpful_count"]
        session_quality.messages_with_feedback = stats["total_feedback"]

        # Calculate session success based on feedback
        # Session is successful if:
        # - Has positive feedback AND no negative feedback, OR
        # - More than 60% of feedback is positive
        helpful_percentage = stats["helpful_percentage"]
        session_quality.session_success = (
            (stats["helpful_count"] > 0 and stats["not_helpful_count"] == 0) or
            (helpful_percentage >= 0.6)
        )

        # Update success indicators
        session_quality.success_indicators = {
            "has_positive_feedback": stats["helpful_count"] > 0,
            "no_negative_feedback": stats["not_helpful_count"] == 0,
            "helpful_percentage": helpful_percentage
        }

        self.db.commit()

        logger.info(
            "Updated session quality",
            tenant_id=tenant_id,
            session_id=session_id,
            session_success=session_quality.session_success,
            helpful_count=stats["helpful_count"],
            not_helpful_count=stats["not_helpful_count"]
        )

        # Publish session quality updated event
        try:
            asyncio.create_task(event_publisher.publish_session_quality_updated(
                tenant_id=tenant_id,
                session_id=session_id,
                session_success=session_quality.session_success,
                helpful_count=stats["helpful_count"],
                not_helpful_count=stats["not_helpful_count"]
            ))
        except Exception as e:
            logger.exception(f"Failed to publish session quality event: {e}")
