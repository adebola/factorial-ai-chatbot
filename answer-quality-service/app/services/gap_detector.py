"""
Knowledge Gap Detection Service

Uses TF-IDF and clustering to identify recurring questions with low-quality answers.
"""

from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime, timedelta
import uuid
from collections import defaultdict

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

from app.models.quality_metrics import RAGQualityMetrics
from app.models.feedback import AnswerFeedback
from app.models.knowledge_gap import KnowledgeGap
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class GapDetector:
    """
    Detects knowledge gaps by analyzing low-quality responses.

    Uses TF-IDF vectorization and cosine similarity to cluster similar questions.
    """

    def __init__(self, db: Session):
        self.db = db
        self.similarity_threshold = 0.7  # Questions with >70% similarity are grouped
        self.min_occurrences = 2  # Minimum times a question pattern must appear
        self.low_confidence_threshold = 0.5  # Confidence below this is considered low

    def detect_gaps(
        self,
        tenant_id: str,
        days_lookback: int = 7,
        limit: Optional[int] = None
    ) -> List[KnowledgeGap]:
        """
        Detect knowledge gaps for a tenant.

        Args:
            tenant_id: Tenant to analyze
            days_lookback: How many days back to analyze
            limit: Maximum number of gaps to return

        Returns:
            List of detected knowledge gaps
        """
        logger.info(
            "Starting gap detection",
            tenant_id=tenant_id,
            days_lookback=days_lookback
        )

        # Get low-quality messages from the lookback period
        cutoff_date = datetime.now() - timedelta(days=days_lookback)

        low_quality_messages = self._get_low_quality_messages(
            tenant_id=tenant_id,
            since=cutoff_date
        )

        if not low_quality_messages:
            logger.info(
                "No low-quality messages found",
                tenant_id=tenant_id
            )
            return []

        logger.info(
            f"Found {len(low_quality_messages)} low-quality messages",
            tenant_id=tenant_id,
            count=len(low_quality_messages)
        )

        # Cluster similar questions
        question_clusters = self._cluster_questions(low_quality_messages)

        # Create or update knowledge gaps
        gaps = []
        for cluster in question_clusters:
            if len(cluster['questions']) >= self.min_occurrences:
                gap = self._create_or_update_gap(
                    tenant_id=tenant_id,
                    cluster=cluster
                )
                if gap:
                    gaps.append(gap)

        logger.info(
            f"Detected {len(gaps)} knowledge gaps",
            tenant_id=tenant_id,
            gaps_count=len(gaps)
        )

        if limit:
            gaps = gaps[:limit]

        return gaps

    def _get_low_quality_messages(
        self,
        tenant_id: str,
        since: datetime
    ) -> List[Dict]:
        """
        Get messages with low quality indicators.

        A message is low-quality if:
        - Confidence score < threshold
        - Retrieval score is low
        - Received negative feedback
        """
        # Get messages with low confidence or retrieval scores
        low_quality_metrics = self.db.query(RAGQualityMetrics).filter(
            and_(
                RAGQualityMetrics.tenant_id == tenant_id,
                RAGQualityMetrics.created_at >= since,
                RAGQualityMetrics.answer_confidence < self.low_confidence_threshold
            )
        ).all()

        # Also get messages with negative feedback
        negative_feedback = self.db.query(AnswerFeedback).filter(
            and_(
                AnswerFeedback.tenant_id == tenant_id,
                AnswerFeedback.created_at >= since,
                AnswerFeedback.feedback_type == "not_helpful"
            )
        ).all()

        # Combine into a map: message_id -> quality info
        message_quality = {}

        for metric in low_quality_metrics:
            # Get the user question from session
            # For now, we'll use the content_preview which should be the question
            message_quality[metric.message_id] = {
                'question': metric.content_preview or "",
                'confidence': metric.answer_confidence,
                'retrieval_score': metric.retrieval_score,
                'has_negative_feedback': False,
                'message_id': metric.message_id,
                'session_id': metric.session_id
            }

        for feedback in negative_feedback:
            if feedback.message_id in message_quality:
                message_quality[feedback.message_id]['has_negative_feedback'] = True
            else:
                # Add messages with negative feedback even if confidence was OK
                message_quality[feedback.message_id] = {
                    'question': "",  # We don't have the question text
                    'confidence': None,
                    'retrieval_score': None,
                    'has_negative_feedback': True,
                    'message_id': feedback.message_id,
                    'session_id': feedback.session_id
                }

        # Filter out messages without question text
        return [
            msg_data for msg_data in message_quality.values()
            if msg_data['question'].strip()
        ]

    def _cluster_questions(self, messages: List[Dict]) -> List[Dict]:
        """
        Cluster similar questions using TF-IDF and cosine similarity.

        Args:
            messages: List of message dictionaries with 'question' field

        Returns:
            List of clusters, each containing similar questions
        """
        if not messages:
            return []

        # Extract questions
        questions = [msg['question'] for msg in messages]

        if len(questions) < 2:
            # Only one question, can't cluster
            return [{
                'pattern': questions[0],
                'questions': [messages[0]],
                'avg_confidence': messages[0]['confidence']
            }]

        # Create TF-IDF vectors
        try:
            vectorizer = TfidfVectorizer(
                max_features=100,
                stop_words='english',
                ngram_range=(1, 2),
                min_df=1
            )
            tfidf_matrix = vectorizer.fit_transform(questions)

            # Compute similarity matrix
            similarity_matrix = cosine_similarity(tfidf_matrix)

            # Cluster questions based on similarity
            clusters = []
            assigned = set()

            for i in range(len(questions)):
                if i in assigned:
                    continue

                # Start a new cluster
                cluster_messages = [messages[i]]
                assigned.add(i)

                # Find similar questions
                for j in range(i + 1, len(questions)):
                    if j in assigned:
                        continue

                    if similarity_matrix[i][j] >= self.similarity_threshold:
                        cluster_messages.append(messages[j])
                        assigned.add(j)

                # Calculate cluster statistics
                confidences = [
                    msg['confidence']
                    for msg in cluster_messages
                    if msg['confidence'] is not None
                ]
                avg_confidence = sum(confidences) / len(confidences) if confidences else None

                negative_count = sum(
                    1 for msg in cluster_messages
                    if msg['has_negative_feedback']
                )

                # Use the first question as the pattern (could be improved)
                clusters.append({
                    'pattern': cluster_messages[0]['question'],
                    'questions': cluster_messages,
                    'avg_confidence': avg_confidence,
                    'negative_feedback_count': negative_count
                })

            return clusters

        except Exception as e:
            logger.error(
                f"Error clustering questions: {e}",
                error=str(e))
            # Return each question as its own cluster
            return [
                {
                    'pattern': msg['question'],
                    'questions': [msg],
                    'avg_confidence': msg['confidence'],
                    'negative_feedback_count': 1 if msg['has_negative_feedback'] else 0
                }
                for msg in messages
            ]

    def _create_or_update_gap(
        self,
        tenant_id: str,
        cluster: Dict
    ) -> Optional[KnowledgeGap]:
        """
        Create a new knowledge gap or update an existing one.

        Args:
            tenant_id: Tenant ID
            cluster: Cluster of similar questions

        Returns:
            KnowledgeGap instance or None
        """
        try:
            pattern = cluster['pattern'][:500]  # Truncate to reasonable length

            # Check if similar gap already exists
            existing_gap = self.db.query(KnowledgeGap).filter(
                and_(
                    KnowledgeGap.tenant_id == tenant_id,
                    KnowledgeGap.question_pattern == pattern,
                    KnowledgeGap.status != "resolved"
                )
            ).first()

            example_questions = [msg['question'] for msg in cluster['questions'][:5]]

            if existing_gap:
                # Update existing gap
                existing_gap.occurrence_count += len(cluster['questions'])
                existing_gap.example_questions = example_questions
                existing_gap.avg_confidence = cluster['avg_confidence']
                existing_gap.negative_feedback_count += cluster['negative_feedback_count']
                existing_gap.last_occurrence_at = datetime.now()

                self.db.commit()
                logger.info(
                    "Updated existing knowledge gap",
                    gap_id=existing_gap.id,
                    tenant_id=tenant_id
                )
                return existing_gap
            else:
                # Create new gap
                gap = KnowledgeGap(
                    id=str(uuid.uuid4()),
                    tenant_id=tenant_id,
                    question_pattern=pattern,
                    example_questions=example_questions,
                    occurrence_count=len(cluster['questions']),
                    avg_confidence=cluster['avg_confidence'],
                    negative_feedback_count=cluster['negative_feedback_count'],
                    status="detected"
                )

                self.db.add(gap)
                self.db.commit()

                logger.info(
                    "Created new knowledge gap",
                    gap_id=gap.id,
                    tenant_id=tenant_id,
                    pattern=pattern[:50]
                )

                return gap

        except Exception as e:
            logger.error(
                f"Error creating/updating gap: {e}",
                error=str(e))
            self.db.rollback()
            return None

    def acknowledge_gap(self, gap_id: str, notes: Optional[str] = None) -> bool:
        """
        Mark a knowledge gap as acknowledged by admin.

        Args:
            gap_id: Gap ID to acknowledge
            notes: Optional admin notes

        Returns:
            True if successful
        """
        try:
            gap = self.db.query(KnowledgeGap).filter(
                KnowledgeGap.id == gap_id
            ).first()

            if not gap:
                return False

            gap.status = "acknowledged"
            if notes:
                gap.resolution_notes = notes

            self.db.commit()

            logger.info(
                "Acknowledged knowledge gap",
                gap_id=gap_id,
                tenant_id=gap.tenant_id
            )

            return True

        except Exception as e:
            logger.error(
                f"Error acknowledging gap: {e}",
                gap_id=gap_id,
                error=str(e)
            )
            self.db.rollback()
            return False

    def resolve_gap(
        self,
        gap_id: str,
        resolution_notes: str
    ) -> bool:
        """
        Mark a knowledge gap as resolved.

        Args:
            gap_id: Gap ID to resolve
            resolution_notes: How the gap was resolved

        Returns:
            True if successful
        """
        try:
            gap = self.db.query(KnowledgeGap).filter(
                KnowledgeGap.id == gap_id
            ).first()

            if not gap:
                return False

            gap.status = "resolved"
            gap.resolved_at = datetime.now()
            gap.resolution_notes = resolution_notes

            self.db.commit()

            logger.info(
                "Resolved knowledge gap",
                gap_id=gap_id,
                tenant_id=gap.tenant_id
            )

            return True

        except Exception as e:
            logger.error(
                f"Error resolving gap: {e}",
                gap_id=gap_id,
                error=str(e)
            )
            self.db.rollback()
            return False
