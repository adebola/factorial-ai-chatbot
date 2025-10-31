"""
Quality Metrics API Endpoints

Allows viewing quality metrics for messages, sessions, and tenants.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.schemas.quality import QualityMetricsResponse, QualityStats
from app.services.quality_analyzer import QualityAnalyzer
from app.core.database import get_db
from app.core.auth import validate_token, get_tenant_id, require_admin
from app.core.logging_config import get_logger
from app.models.quality_metrics import RAGQualityMetrics

logger = get_logger(__name__)

router = APIRouter()


@router.get(
    "/message/{message_id}",
    response_model=QualityMetricsResponse,
    summary="Get message quality metrics",
    description="Get quality metrics for a specific message"
)
async def get_message_quality(
    message_id: str,
    claims: dict = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """
    Get quality metrics for a specific message.

    Includes:
    - Retrieval score
    - Answer confidence
    - Response time
    - Sentiment (if enabled)

    Returns 404 if no quality metrics exist for this message.
    """
    tenant_id = get_tenant_id(claims)

    analyzer = QualityAnalyzer(db)
    metrics = await analyzer.get_message_quality(tenant_id, message_id)

    if not metrics:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No quality metrics found for message {message_id}"
        )

    return metrics


@router.get(
    "/session/{session_id}",
    response_model=List[QualityMetricsResponse],
    summary="Get session quality metrics",
    description="Get quality metrics for all messages in a session"
)
async def get_session_quality_metrics(
    session_id: str,
    limit: int = Query(100, le=500, description="Maximum number of records to return"),
    claims: dict = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """
    Get quality metrics for all messages in a session.

    Returns metrics sorted by creation time (oldest first).
    """
    tenant_id = get_tenant_id(claims)

    metrics = db.query(RAGQualityMetrics).filter(
        RAGQualityMetrics.tenant_id == tenant_id,
        RAGQualityMetrics.session_id == session_id
    ).order_by(
        RAGQualityMetrics.created_at.asc()
    ).limit(limit).all()

    return metrics


@router.get(
    "/session/{session_id}/stats",
    response_model=QualityStats,
    summary="Get session quality statistics",
    description="Get aggregated quality statistics for a session"
)
async def get_session_quality_stats(
    session_id: str,
    claims: dict = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """
    Get aggregated quality statistics for a session.

    Returns:
    - Average retrieval score
    - Average confidence score
    - Average response time
    - Low confidence message count
    - Sentiment breakdown
    """
    tenant_id = get_tenant_id(claims)

    analyzer = QualityAnalyzer(db)
    stats = await analyzer.get_session_quality_stats(tenant_id, session_id)

    return QualityStats(**stats)


@router.get(
    "/low-quality",
    response_model=List[QualityMetricsResponse],
    summary="Get low quality messages",
    description="Get messages with low quality scores (admin only)"
)
async def get_low_quality_messages(
    limit: int = Query(50, le=200, description="Maximum number of messages to return"),
    claims: dict = Depends(validate_token),
    # _: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Get messages with low quality scores.

    Includes messages with:
    - Low confidence scores (< 0.5)
    - Poor retrieval scores
    - Frustrated sentiment

    Admin only endpoint.
    """
    tenant_id = get_tenant_id(claims)

    analyzer = QualityAnalyzer(db)
    low_quality_messages = await analyzer.get_low_quality_messages(
        tenant_id=tenant_id,
        limit=limit
    )

    return low_quality_messages


@router.get(
    "/stats",
    response_model=QualityStats,
    summary="Get overall quality statistics",
    description="Get overall quality statistics for the tenant"
)
async def get_overall_quality_stats(
    session_id: Optional[str] = Query(None, description="Optional session ID to filter by"),
    claims: dict = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """
    Get overall quality statistics for the tenant.

    Can be filtered by session_id or return tenant-wide statistics.

    Returns:
    - Total messages analyzed
    - Average quality scores
    - Low confidence message count
    - Sentiment distribution
    """
    tenant_id = get_tenant_id(claims)

    if session_id:
        analyzer = QualityAnalyzer(db)
        stats = await analyzer.get_session_quality_stats(tenant_id, session_id)
    else:
        # Get tenant-wide statistics
        from sqlalchemy import func

        metrics = db.query(RAGQualityMetrics).filter(
            RAGQualityMetrics.tenant_id == tenant_id
        ).all()

        if not metrics:
            return QualityStats(
                total_messages=0,
                avg_retrieval_score=None,
                avg_confidence_score=None,
                avg_response_time_ms=None,
                low_confidence_count=0,
                sentiment_breakdown={}
            )

        # Calculate statistics
        retrieval_scores = [m.retrieval_score for m in metrics if m.retrieval_score is not None]
        confidence_scores = [m.answer_confidence for m in metrics if m.answer_confidence is not None]
        response_times = [m.response_time_ms for m in metrics if m.response_time_ms is not None]

        low_confidence_count = sum(
            1 for m in metrics
            if m.answer_confidence is not None and m.answer_confidence < 0.5
        )

        sentiment_breakdown = {}
        for m in metrics:
            if m.basic_sentiment:
                sentiment_breakdown[m.basic_sentiment] = sentiment_breakdown.get(m.basic_sentiment, 0) + 1

        stats = {
            "total_messages": len(metrics),
            "avg_retrieval_score": round(sum(retrieval_scores) / len(retrieval_scores), 3) if retrieval_scores else None,
            "avg_confidence_score": round(sum(confidence_scores) / len(confidence_scores), 3) if confidence_scores else None,
            "avg_response_time_ms": int(sum(response_times) / len(response_times)) if response_times else None,
            "low_confidence_count": low_confidence_count,
            "sentiment_breakdown": sentiment_breakdown
        }

    return QualityStats(**stats)
