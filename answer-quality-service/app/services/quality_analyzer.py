"""
Quality Analyzer Service

Analyzes RAG quality metrics and stores them in the database.
Flags low-quality answers for admin review.
"""

import uuid
from datetime import datetime
from typing import Optional, Dict
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.models.quality_metrics import RAGQualityMetrics
from app.models.knowledge_gap import KnowledgeGap
from app.services.sentiment_analyzer import sentiment_analyzer
from app.core.logging_config import get_logger, log_quality_analysis
from app.core.config import settings

logger = get_logger(__name__)


class QualityAnalyzer:
    """Analyze and store RAG quality metrics"""

    # Thresholds for quality warnings
    LOW_CONFIDENCE_THRESHOLD = settings.LOW_CONFIDENCE_THRESHOLD  # 0.5
    LOW_RETRIEVAL_THRESHOLD = 0.4
    HIGH_RESPONSE_TIME_THRESHOLD = 3000  # 3 seconds

    def __init__(self, db: Session):
        self.db = db

    async def analyze_message_quality(
        self,
        tenant_id: str,
        message_id: str,
        session_id: str,
        metrics: Dict,
        content: Optional[str] = None,
        user_question: Optional[str] = None
    ) -> RAGQualityMetrics:
        """
        Analyze and store quality metrics for a message.

        Args:
            tenant_id: Tenant ID
            message_id: Message ID
            session_id: Session ID
            metrics: Quality metrics from chat service
            content: Optional message content for sentiment analysis
            user_question: Optional user question that triggered this response

        Returns:
            Created quality metrics record
        """
        import time
        start_time = time.time()

        # Check if metrics already exist for this message
        existing_metrics = self.db.query(RAGQualityMetrics).filter(
            RAGQualityMetrics.message_id == message_id
        ).first()

        if existing_metrics:
            logger.info(
                "Quality metrics already exist for message",
                message_id=message_id
            )
            return existing_metrics

        # Create quality metrics record
        is_knowledge_gap = metrics.get("is_knowledge_gap", False)
        quality_record = RAGQualityMetrics(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            session_id=session_id,
            message_id=message_id,
            retrieval_score=metrics.get("retrieval_score"),
            documents_retrieved=metrics.get("documents_retrieved"),
            answer_confidence=metrics.get("answer_confidence"),
            sources_cited=metrics.get("sources_cited"),
            answer_length=metrics.get("answer_length"),
            response_time_ms=metrics.get("response_time_ms"),
            user_question=user_question[:500] if user_question else None,
            is_knowledge_gap=is_knowledge_gap,
        )

        # Perform sentiment analysis if enabled and content provided
        if settings.ENABLE_BASIC_SENTIMENT and content:
            sentiment_result = sentiment_analyzer.analyze(content)
            if sentiment_result.get("enabled"):
                quality_record.basic_sentiment = sentiment_result.get("label")
                quality_record.sentiment_confidence = sentiment_result.get("score")

        # Save to database
        self.db.add(quality_record)
        self.db.commit()
        self.db.refresh(quality_record)

        duration_ms = round((time.time() - start_time) * 1000, 2)

        # Log quality analysis
        log_quality_analysis(
            tenant_id=tenant_id,
            message_id=message_id,
            retrieval_score=quality_record.retrieval_score or 0.0,
            answer_confidence=quality_record.answer_confidence or 0.0,
            duration_ms=duration_ms
        )

        # Check for quality issues and flag them
        await self._check_quality_issues(quality_record)

        return quality_record

    async def _check_quality_issues(self, quality_record: RAGQualityMetrics):
        """
        Check for quality issues and log warnings.

        Args:
            quality_record: Quality metrics record to check
        """
        issues = []

        # Check for low confidence
        if (quality_record.answer_confidence is not None and
            quality_record.answer_confidence < self.LOW_CONFIDENCE_THRESHOLD):
            issues.append("low_confidence")
            logger.warning(
                "Low confidence answer detected",
                tenant_id=quality_record.tenant_id,
                message_id=quality_record.message_id,
                confidence=quality_record.answer_confidence
            )

        # Check for poor retrieval
        if (quality_record.retrieval_score is not None and
            quality_record.retrieval_score < self.LOW_RETRIEVAL_THRESHOLD):
            issues.append("poor_retrieval")
            logger.warning(
                "Poor retrieval score detected",
                tenant_id=quality_record.tenant_id,
                message_id=quality_record.message_id,
                retrieval_score=quality_record.retrieval_score
            )

        # Check for slow response time
        if (quality_record.response_time_ms is not None and
            quality_record.response_time_ms > self.HIGH_RESPONSE_TIME_THRESHOLD):
            issues.append("slow_response")
            logger.warning(
                "Slow response time detected",
                tenant_id=quality_record.tenant_id,
                message_id=quality_record.message_id,
                response_time_ms=quality_record.response_time_ms
            )

        # Check for frustrated sentiment
        if quality_record.basic_sentiment == "frustrated":
            issues.append("frustrated_user")
            logger.warning(
                "Frustrated user detected via sentiment",
                tenant_id=quality_record.tenant_id,
                message_id=quality_record.message_id,
                sentiment=quality_record.basic_sentiment
            )

        # If multiple issues, this is a high-priority problem
        if len(issues) >= 2:
            logger.error(
                "Multiple quality issues detected",
                tenant_id=quality_record.tenant_id,
                message_id=quality_record.message_id,
                issues=issues
            )

        # Real-time knowledge gap flagging
        if quality_record.is_knowledge_gap and quality_record.user_question:
            await self._create_immediate_gap(quality_record)

    async def _create_immediate_gap(self, quality_record: RAGQualityMetrics):
        """
        Immediately create a KnowledgeGap record for a definitive "can't answer" response.

        If an existing unresolved gap with the same question pattern exists for this tenant,
        increment its occurrence_count instead of creating a duplicate.
        """
        try:
            question_pattern = quality_record.user_question[:500]

            # Check for existing unresolved gap with the same pattern
            existing_gap = self.db.query(KnowledgeGap).filter(
                and_(
                    KnowledgeGap.tenant_id == quality_record.tenant_id,
                    KnowledgeGap.question_pattern == question_pattern,
                    KnowledgeGap.status != "resolved"
                )
            ).first()

            if existing_gap:
                existing_gap.occurrence_count += 1
                existing_gap.last_occurrence_at = datetime.now()
                # Append to example_questions if not already full
                examples = existing_gap.example_questions or []
                if len(examples) < 5:
                    examples.append(question_pattern)
                    existing_gap.example_questions = examples
                self.db.commit()
                logger.info(
                    "Updated existing knowledge gap",
                    gap_id=existing_gap.id,
                    tenant_id=quality_record.tenant_id,
                    occurrence_count=existing_gap.occurrence_count
                )
            else:
                gap = KnowledgeGap(
                    id=str(uuid.uuid4()),
                    tenant_id=quality_record.tenant_id,
                    question_pattern=question_pattern,
                    example_questions=[question_pattern],
                    occurrence_count=1,
                    avg_confidence=quality_record.answer_confidence,
                    negative_feedback_count=0,
                    status="detected"
                )
                self.db.add(gap)
                self.db.commit()
                logger.info(
                    "Created immediate knowledge gap",
                    gap_id=gap.id,
                    tenant_id=quality_record.tenant_id,
                    question=question_pattern[:50]
                )
        except Exception as e:
            logger.error(
                f"Error creating immediate knowledge gap: {e}",
                tenant_id=quality_record.tenant_id,
                message_id=quality_record.message_id
            )
            self.db.rollback()

    async def get_message_quality(
        self,
        tenant_id: str,
        message_id: str
    ) -> Optional[RAGQualityMetrics]:
        """
        Get quality metrics for a specific message.

        Args:
            tenant_id: Tenant ID
            message_id: Message ID

        Returns:
            Quality metrics record or None if not found
        """
        return self.db.query(RAGQualityMetrics).filter(
            RAGQualityMetrics.tenant_id == tenant_id,
            RAGQualityMetrics.message_id == message_id
        ).first()

    async def get_session_quality_stats(
        self,
        tenant_id: str,
        session_id: str
    ) -> Dict:
        """
        Get aggregated quality statistics for a session.

        Args:
            tenant_id: Tenant ID
            session_id: Session ID

        Returns:
            Dictionary with quality statistics
        """
        from sqlalchemy import func

        # Get all quality metrics for this session
        metrics = self.db.query(RAGQualityMetrics).filter(
            RAGQualityMetrics.tenant_id == tenant_id,
            RAGQualityMetrics.session_id == session_id
        ).all()

        if not metrics:
            return {
                "total_messages": 0,
                "avg_retrieval_score": None,
                "avg_confidence_score": None,
                "avg_response_time_ms": None,
                "low_confidence_count": 0,
                "sentiment_breakdown": {}
            }

        # Calculate averages
        retrieval_scores = [m.retrieval_score for m in metrics if m.retrieval_score is not None]
        confidence_scores = [m.answer_confidence for m in metrics if m.answer_confidence is not None]
        response_times = [m.response_time_ms for m in metrics if m.response_time_ms is not None]

        # Count low confidence messages
        low_confidence_count = sum(
            1 for m in metrics
            if m.answer_confidence is not None and m.answer_confidence < self.LOW_CONFIDENCE_THRESHOLD
        )

        # Sentiment breakdown
        sentiment_breakdown = {}
        for m in metrics:
            if m.basic_sentiment:
                sentiment_breakdown[m.basic_sentiment] = sentiment_breakdown.get(m.basic_sentiment, 0) + 1

        return {
            "total_messages": len(metrics),
            "avg_retrieval_score": round(sum(retrieval_scores) / len(retrieval_scores), 3) if retrieval_scores else None,
            "avg_confidence_score": round(sum(confidence_scores) / len(confidence_scores), 3) if confidence_scores else None,
            "avg_response_time_ms": int(sum(response_times) / len(response_times)) if response_times else None,
            "low_confidence_count": low_confidence_count,
            "sentiment_breakdown": sentiment_breakdown
        }

    async def get_low_quality_messages(
        self,
        tenant_id: str,
        limit: int = 50
    ) -> list:
        """
        Get messages with low quality scores.

        Args:
            tenant_id: Tenant ID
            limit: Maximum number of messages to return

        Returns:
            List of low-quality message records
        """
        return self.db.query(RAGQualityMetrics).filter(
            RAGQualityMetrics.tenant_id == tenant_id,
            RAGQualityMetrics.answer_confidence < self.LOW_CONFIDENCE_THRESHOLD
        ).order_by(
            RAGQualityMetrics.answer_confidence.asc(),
            RAGQualityMetrics.created_at.desc()
        ).limit(limit).all()
