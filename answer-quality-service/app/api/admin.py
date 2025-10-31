"""
Admin Dashboard API

Endpoints for admin users to view quality trends, insights, and knowledge gaps.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, desc
from typing import List, Optional
from datetime import datetime, timedelta
import csv
import io

from app.core.database import get_db
from app.core.auth import validate_token, require_admin
from app.models.quality_metrics import RAGQualityMetrics
from app.models.feedback import AnswerFeedback
from app.models.knowledge_gap import KnowledgeGap
from app.models.session_quality import SessionQuality
from app.services.gap_detector import GapDetector
from app.core.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/dashboard/overview")
async def get_dashboard_overview(
    days: int = Query(default=7, ge=1, le=90, description="Days to look back"),
    current_user: dict = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """
    Get overview statistics for dashboard.

    Requires authentication. Returns data for the user's tenant only.
    """
    tenant_id = current_user["tenant_id"]
    cutoff_date = datetime.now() - timedelta(days=days)

    # Total messages analyzed
    total_messages = db.query(func.count(RAGQualityMetrics.id)).filter(
        and_(
            RAGQualityMetrics.tenant_id == tenant_id,
            RAGQualityMetrics.created_at >= cutoff_date
        )
    ).scalar() or 0

    # Average quality scores
    avg_stats = db.query(
        func.avg(RAGQualityMetrics.answer_confidence).label('avg_confidence'),
        func.avg(RAGQualityMetrics.retrieval_score).label('avg_retrieval'),
        func.avg(RAGQualityMetrics.response_time_ms).label('avg_response_time')
    ).filter(
        and_(
            RAGQualityMetrics.tenant_id == tenant_id,
            RAGQualityMetrics.created_at >= cutoff_date
        )
    ).first()

    # Feedback statistics
    feedback_stats = db.query(
        AnswerFeedback.feedback_type,
        func.count(AnswerFeedback.id).label('count')
    ).filter(
        and_(
            AnswerFeedback.tenant_id == tenant_id,
            AnswerFeedback.created_at >= cutoff_date
        )
    ).group_by(AnswerFeedback.feedback_type).all()

    feedback_summary = {ft: 0 for ft in ['helpful', 'not_helpful']}
    for feedback_type, count in feedback_stats:
        feedback_summary[feedback_type] = count

    # Knowledge gaps
    active_gaps = db.query(func.count(KnowledgeGap.id)).filter(
        and_(
            KnowledgeGap.tenant_id == tenant_id,
            KnowledgeGap.status.in_(['detected', 'acknowledged'])
        )
    ).scalar() or 0

    # Low quality messages
    low_quality_count = db.query(func.count(RAGQualityMetrics.id)).filter(
        and_(
            RAGQualityMetrics.tenant_id == tenant_id,
            RAGQualityMetrics.created_at >= cutoff_date,
            RAGQualityMetrics.answer_confidence < 0.5
        )
    ).scalar() or 0

    logger.info(
        "Dashboard overview requested",
        tenant_id=tenant_id,
        days=days,
        user_id=current_user.get("user_id")
    )

    return {
        "period": {
            "days": days,
            "start_date": cutoff_date.isoformat(),
            "end_date": datetime.now().isoformat()
        },
        "metrics": {
            "total_messages": total_messages,
            "avg_confidence": round(avg_stats.avg_confidence, 3) if avg_stats.avg_confidence else None,
            "avg_retrieval_score": round(avg_stats.avg_retrieval, 3) if avg_stats.avg_retrieval else None,
            "avg_response_time_ms": round(avg_stats.avg_response_time, 0) if avg_stats.avg_response_time else None,
            "low_quality_count": low_quality_count,
            "low_quality_percentage": round((low_quality_count / total_messages * 100), 1) if total_messages > 0 else 0
        },
        "feedback": {
            "helpful": feedback_summary['helpful'],
            "not_helpful": feedback_summary['not_helpful'],
            "total": sum(feedback_summary.values()),
            "helpful_percentage": round(
                (feedback_summary['helpful'] / sum(feedback_summary.values()) * 100), 1
            ) if sum(feedback_summary.values()) > 0 else 0
        },
        "knowledge_gaps": {
            "active_gaps": active_gaps
        }
    }


@router.get("/dashboard/trends")
async def get_quality_trends(
    days: int = Query(default=30, ge=7, le=90, description="Days to analyze"),
    current_user: dict = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """
    Get quality trends over time (daily aggregates).

    Requires authentication. Returns data for the user's tenant only.
    """
    tenant_id = current_user["tenant_id"]
    cutoff_date = datetime.now() - timedelta(days=days)

    # Daily quality metrics
    daily_metrics = db.query(
        func.date(RAGQualityMetrics.created_at).label('date'),
        func.count(RAGQualityMetrics.id).label('message_count'),
        func.avg(RAGQualityMetrics.answer_confidence).label('avg_confidence'),
        func.avg(RAGQualityMetrics.retrieval_score).label('avg_retrieval')
    ).filter(
        and_(
            RAGQualityMetrics.tenant_id == tenant_id,
            RAGQualityMetrics.created_at >= cutoff_date
        )
    ).group_by(func.date(RAGQualityMetrics.created_at)).order_by('date').all()

    # Daily feedback counts
    daily_feedback = db.query(
        func.date(AnswerFeedback.created_at).label('date'),
        AnswerFeedback.feedback_type,
        func.count(AnswerFeedback.id).label('count')
    ).filter(
        and_(
            AnswerFeedback.tenant_id == tenant_id,
            AnswerFeedback.created_at >= cutoff_date
        )
    ).group_by(
        func.date(AnswerFeedback.created_at),
        AnswerFeedback.feedback_type
    ).all()

    # Format trends data
    trends = []
    for metric in daily_metrics:
        trends.append({
            "date": metric.date.isoformat(),
            "message_count": metric.message_count,
            "avg_confidence": round(metric.avg_confidence, 3) if metric.avg_confidence else None,
            "avg_retrieval": round(metric.avg_retrieval, 3) if metric.avg_retrieval else None
        })

    # Add feedback to trends
    feedback_by_date = {}
    for fb in daily_feedback:
        date_str = fb.date.isoformat()
        if date_str not in feedback_by_date:
            feedback_by_date[date_str] = {'helpful': 0, 'not_helpful': 0}
        feedback_by_date[date_str][fb.feedback_type] = fb.count

    for trend in trends:
        date_str = trend['date']
        if date_str in feedback_by_date:
            trend['feedback'] = feedback_by_date[date_str]
        else:
            trend['feedback'] = {'helpful': 0, 'not_helpful': 0}

    logger.info(
        "Quality trends requested",
        tenant_id=tenant_id,
        days=days,
        data_points=len(trends)
    )

    return {
        "period": {
            "days": days,
            "start_date": cutoff_date.isoformat(),
            "end_date": datetime.now().isoformat()
        },
        "trends": trends
    }


@router.get("/gaps")
async def list_knowledge_gaps(
    status: Optional[str] = Query(None, regex="^(detected|acknowledged|resolved)$"),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: dict = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """
    List knowledge gaps for the tenant.

    Requires authentication. Returns gaps for the user's tenant only.
    """
    tenant_id = current_user["tenant_id"]

    query = db.query(KnowledgeGap).filter(
        KnowledgeGap.tenant_id == tenant_id
    )

    if status:
        query = query.filter(KnowledgeGap.status == status)

    gaps = query.order_by(
        desc(KnowledgeGap.occurrence_count),
        desc(KnowledgeGap.last_occurrence_at)
    ).limit(limit).all()

    logger.info(
        "Knowledge gaps listed",
        tenant_id=tenant_id,
        status_filter=status,
        count=len(gaps)
    )

    return {
        "count": len(gaps),
        "gaps": [
            {
                "id": gap.id,
                "question_pattern": gap.question_pattern,
                "example_questions": gap.example_questions,
                "occurrence_count": gap.occurrence_count,
                "avg_confidence": round(gap.avg_confidence, 3) if gap.avg_confidence else None,
                "negative_feedback_count": gap.negative_feedback_count,
                "status": gap.status,
                "first_detected_at": gap.first_detected_at.isoformat(),
                "last_occurrence_at": gap.last_occurrence_at.isoformat(),
                "resolved_at": gap.resolved_at.isoformat() if gap.resolved_at else None,
                "resolution_notes": gap.resolution_notes
            }
            for gap in gaps
        ]
    }


@router.post("/gaps/detect")
async def trigger_gap_detection(
    days: int = Query(default=7, ge=1, le=30),
    current_user: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Manually trigger knowledge gap detection.

    Requires admin role.
    """
    tenant_id = current_user["tenant_id"]

    logger.info(
        "Manual gap detection triggered",
        tenant_id=tenant_id,
        days=days,
        user_id=current_user.get("user_id")
    )

    try:
        detector = GapDetector(db)
        gaps = detector.detect_gaps(tenant_id=tenant_id, days_lookback=days)

        return {
            "success": True,
            "gaps_detected": len(gaps),
            "gaps": [
                {
                    "id": gap.id,
                    "question_pattern": gap.question_pattern[:100],
                    "occurrence_count": gap.occurrence_count,
                    "status": gap.status
                }
                for gap in gaps
            ]
        }

    except Exception as e:
        logger.error(
            f"Gap detection failed: {e}",
            tenant_id=tenant_id,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gap detection failed: {str(e)}"
        )


@router.patch("/gaps/{gap_id}/acknowledge")
async def acknowledge_gap(
    gap_id: str,
    notes: Optional[str] = None,
    current_user: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Acknowledge a knowledge gap.

    Requires admin role.
    """
    tenant_id = current_user["tenant_id"]

    # Verify gap belongs to tenant
    gap = db.query(KnowledgeGap).filter(
        and_(
            KnowledgeGap.id == gap_id,
            KnowledgeGap.tenant_id == tenant_id
        )
    ).first()

    if not gap:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge gap not found"
        )

    detector = GapDetector(db)
    success = detector.acknowledge_gap(gap_id=gap_id, notes=notes)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to acknowledge gap"
        )

    return {"success": True, "gap_id": gap_id, "status": "acknowledged"}


@router.patch("/gaps/{gap_id}/resolve")
async def resolve_gap(
    gap_id: str,
    resolution_notes: str,
    current_user: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Mark a knowledge gap as resolved.

    Requires admin role.
    """
    tenant_id = current_user["tenant_id"]

    # Verify gap belongs to tenant
    gap = db.query(KnowledgeGap).filter(
        and_(
            KnowledgeGap.id == gap_id,
            KnowledgeGap.tenant_id == tenant_id
        )
    ).first()

    if not gap:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge gap not found"
        )

    detector = GapDetector(db)
    success = detector.resolve_gap(gap_id=gap_id, resolution_notes=resolution_notes)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to resolve gap"
        )

    return {"success": True, "gap_id": gap_id, "status": "resolved"}


@router.get("/export/quality-report")
async def export_quality_report(
    days: int = Query(default=30, ge=1, le=90),
    format: str = Query(default="csv", regex="^(csv)$"),
    current_user: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Export quality metrics report as CSV.

    Requires admin role.
    """
    tenant_id = current_user["tenant_id"]
    cutoff_date = datetime.now() - timedelta(days=days)

    # Get quality metrics with feedback
    metrics = db.query(RAGQualityMetrics).filter(
        and_(
            RAGQualityMetrics.tenant_id == tenant_id,
            RAGQualityMetrics.created_at >= cutoff_date
        )
    ).order_by(desc(RAGQualityMetrics.created_at)).all()

    # Get feedback data
    feedback_map = {}
    feedbacks = db.query(AnswerFeedback).filter(
        and_(
            AnswerFeedback.tenant_id == tenant_id,
            AnswerFeedback.created_at >= cutoff_date
        )
    ).all()

    for fb in feedbacks:
        feedback_map[fb.message_id] = {
            'type': fb.feedback_type,
            'comment': fb.comment
        }

    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        'Message ID',
        'Session ID',
        'Created At',
        'Confidence Score',
        'Retrieval Score',
        'Documents Retrieved',
        'Response Time (ms)',
        'Sentiment',
        'Feedback Type',
        'Feedback Comment',
        'Quality Issues'
    ])

    # Data rows
    for metric in metrics:
        feedback = feedback_map.get(metric.message_id, {})

        quality_issues = []
        if metric.low_confidence_flag:
            quality_issues.append('Low Confidence')
        if metric.low_retrieval_flag:
            quality_issues.append('Poor Retrieval')
        if metric.slow_response_flag:
            quality_issues.append('Slow Response')

        writer.writerow([
            metric.message_id,
            metric.session_id,
            metric.created_at.isoformat(),
            metric.answer_confidence,
            metric.retrieval_score,
            metric.documents_retrieved,
            metric.response_time_ms,
            metric.sentiment_label,
            feedback.get('type', ''),
            feedback.get('comment', ''),
            ', '.join(quality_issues)
        ])

    # Return CSV file
    csv_content = output.getvalue()
    output.close()

    logger.info(
        "Quality report exported",
        tenant_id=tenant_id,
        days=days,
        rows=len(metrics)
    )

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=quality-report-{days}days.csv"
        }
    )
