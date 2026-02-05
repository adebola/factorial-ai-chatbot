"""
Admin Dashboard API

Endpoints for admin users to view quality trends, insights, and knowledge gaps.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query, Response, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, desc
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, date
import csv
import io
import httpx
import os

from app.core.database import get_db
from app.core.auth import validate_token, require_admin, require_system_admin
from app.models.quality_metrics import RAGQualityMetrics
from app.models.feedback import AnswerFeedback
from app.models.knowledge_gap import KnowledgeGap
from app.models.session_quality import SessionQuality
from app.services.gap_detector import GapDetector
from app.core.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter()

# Service URLs for inter-service communication
AUTH_SERVICE_URL = os.environ.get("AUTH_SERVICE_URL", "http://localhost:9002")
BILLING_SERVICE_URL = os.environ.get("BILLING_SERVICE_URL", "http://localhost:8004")


@router.get("/dashboard/quick-stats")
async def get_dashboard_quick_stats(
    request: Request,
    current_user: dict = Depends(require_system_admin),
    db: Session = Depends(get_db)
):
    """
    Get today's quick stats for super admin dashboard.

    Requires ROLE_SYSTEM_ADMIN authority.
    Returns today's new tenants, users, revenue, and chats.
    """
    logger.info(
        "System admin requesting quick stats (today)",
        user_id=current_user.get("user_id")
    )

    # Extract authorization token from request headers
    auth_header = request.headers.get("authorization", "")

    # Calculate today's date range
    today_start = datetime.combine(date.today(), datetime.min.time())
    today_end = datetime.combine(date.today(), datetime.max.time())

    # Get today's chat/message counts from local database
    chats_today = db.query(func.count(func.distinct(RAGQualityMetrics.session_id))).filter(
        RAGQualityMetrics.created_at >= today_start
    ).scalar() or 0

    # Call authorization server for today's tenant and user counts
    new_tenants_today = 0
    new_users_today = 0
    try:
        headers = {"Authorization": auth_header} if auth_header else {}
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{AUTH_SERVICE_URL}/auth/api/v1/admin/analytics/platform-metrics",
                headers=headers
            )
            logger.debug(f"Auth server response: {response.json()}")
            if response.status_code == 200:
                data = response.json()
                # Extract today's counts from 30-day data (if available)
                # For now, default to 0 - the auth server would need a "today" endpoint
                new_tenants_today = 0  # TODO: Auth server needs /analytics/today endpoint
                new_users_today = 0
            else:
                logger.warning(f"Auth server returned status {response.status_code}")
    except Exception as e:
        logger.warning(f"Failed to fetch auth metrics: {e}")

    # Call billing service for today's revenue
    revenue_today = 0
    try:
        headers = {"Authorization": auth_header} if auth_header else {}
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Get actual today's revenue from billing service
            response = await client.get(
                f"{BILLING_SERVICE_URL}/api/v1/subscriptions/admin/revenue/today",
                headers=headers
            )
            if response.status_code == 200:
                data = response.json()
                revenue_today = data.get("revenue_today", 0)
            else:
                logger.warning(f"Billing service returned status {response.status_code}")
    except Exception as e:
        logger.warning(f"Failed to fetch billing metrics: {e}")

    logger.info(
        "Quick stats retrieved",
        chats_today=chats_today,
        new_tenants_today=new_tenants_today
    )

    return {
        "new_tenants_today": new_tenants_today,
        "new_users_today": new_users_today,
        "revenue_today": revenue_today,
        "chats_today": chats_today
    }


@router.get("/dashboard/metrics")
async def get_dashboard_metrics(
    request: Request,
    current_user: dict = Depends(require_system_admin),
    db: Session = Depends(get_db)
):
    """
    Get overall platform metrics for super admin dashboard.

    Requires ROLE_SYSTEM_ADMIN authority.
    Returns total tenants, users, chats, messages, and revenue.
    """
    logger.info(
        "System admin requesting dashboard metrics",
        user_id=current_user.get("user_id")
    )

    # Extract authorization token from request headers
    auth_header = request.headers.get("authorization", "")

    # Get total messages and chats from local database
    total_messages = db.query(func.count(RAGQualityMetrics.id)).scalar() or 0
    total_chats = db.query(func.count(func.distinct(RAGQualityMetrics.session_id))).scalar() or 0

    # Call authorization server for tenant and user counts
    total_tenants = 0
    active_tenants = 0
    suspended_tenants = 0
    total_users = 0
    active_users = 0

    try:
        headers = {"Authorization": auth_header} if auth_header else {}
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{AUTH_SERVICE_URL}/auth/api/v1/admin/analytics/platform-metrics",
                headers=headers
            )
            if response.status_code == 200:
                data = response.json()
                tenants_data = data.get("tenants", {})
                users_data = data.get("users", {})

                total_tenants = tenants_data.get("total", 0)
                active_tenants = tenants_data.get("active", 0)
                suspended_tenants = tenants_data.get("inactive", 0)
                total_users = users_data.get("total", 0)
                active_users = users_data.get("active", 0)
            else:
                logger.warning(f"Auth server returned status {response.status_code}: {response.text}")
    except Exception as e:
        logger.error(f"Failed to fetch auth server metrics: {e}")

    # Call billing service for revenue data
    total_revenue = 0
    monthly_revenue = 0

    try:
        headers = {"Authorization": auth_header} if auth_header else {}
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Get analytics from billing service
            response = await client.get(
                f"{BILLING_SERVICE_URL}/api/v1/subscriptions/admin/analytics",
                headers=headers
            )
            if response.status_code == 200:
                data = response.json()
                analytics = data.get("analytics", {})
                monthly_revenue = analytics.get("monthly_revenue", 0)
                yearly_revenue = analytics.get("yearly_revenue", 0)
                total_revenue = monthly_revenue + yearly_revenue
            else:
                logger.warning(f"Billing service returned status {response.status_code}: {response.text}")
    except Exception as e:
        logger.error(f"Failed to fetch billing service metrics: {e}")

    logger.info(
        "Dashboard metrics retrieved",
        total_tenants=total_tenants,
        total_users=total_users,
        total_chats=total_chats,
        total_messages=total_messages
    )

    return {
        "total_tenants": total_tenants,
        "active_tenants": active_tenants,
        "suspended_tenants": suspended_tenants,
        "total_users": total_users,
        "active_users": active_users,
        "total_chats": total_chats,
        "total_messages": total_messages,
        "total_revenue": total_revenue,
        "monthly_revenue": monthly_revenue
    }


@router.get("/dashboard/growth")
async def get_dashboard_growth(
    days: int = Query(default=30, ge=7, le=90, description="Days to analyze"),
    current_user: dict = Depends(require_system_admin),
    db: Session = Depends(get_db)
):
    """
    Get growth trends for super admin dashboard.

    Requires ROLE_SYSTEM_ADMIN authority.
    Returns daily growth data.
    """
    logger.info(
        "System admin requesting growth data",
        user_id=current_user.get("user_id"),
        days=days
    )

    cutoff_date = datetime.now() - timedelta(days=days)

    # Daily message counts
    daily_messages = db.query(
        func.date(RAGQualityMetrics.created_at).label('date'),
        func.count(RAGQualityMetrics.id).label('message_count'),
        func.count(func.distinct(RAGQualityMetrics.session_id)).label('session_count'),
        func.count(func.distinct(RAGQualityMetrics.tenant_id)).label('tenant_count')
    ).filter(
        RAGQualityMetrics.created_at >= cutoff_date
    ).group_by(func.date(RAGQualityMetrics.created_at)).order_by('date').all()

    # Format growth data
    growth_data = [
        {
            "date": metric.date.isoformat(),
            "messages": metric.message_count,
            "sessions": metric.session_count,
            "activeTenants": metric.tenant_count
        }
        for metric in daily_messages
    ]

    logger.info(
        "Growth data retrieved",
        days=days,
        data_points=len(growth_data)
    )

    return {
        "period": {
            "days": days,
            "startDate": cutoff_date.isoformat(),
            "endDate": datetime.now().isoformat()
        },
        "data": growth_data
    }


@router.get("/dashboard/activity")
async def get_dashboard_activity(
    limit: int = Query(default=10, ge=1, le=50, description="Number of recent activities"),
    current_user: dict = Depends(require_system_admin),
    db: Session = Depends(get_db)
):
    """
    Get recent activity for super admin dashboard.

    Requires ROLE_SYSTEM_ADMIN authority.
    Returns recent messages and feedback.
    """
    logger.info(
        "System admin requesting recent activity",
        user_id=current_user.get("user_id"),
        limit=limit
    )

    # Get recent quality metrics
    recent_messages = db.query(RAGQualityMetrics).order_by(
        desc(RAGQualityMetrics.created_at)
    ).limit(limit).all()

    # Get recent feedback
    recent_feedback = db.query(AnswerFeedback).order_by(
        desc(AnswerFeedback.created_at)
    ).limit(limit).all()

    # Get recent knowledge gaps detected
    recent_gaps = db.query(KnowledgeGap).filter(
        KnowledgeGap.status == 'detected'
    ).order_by(
        desc(KnowledgeGap.first_detected_at)
    ).limit(limit).all()

    logger.info(
        "Activity retrieved",
        message_count=len(recent_messages),
        feedback_count=len(recent_feedback),
        gap_count=len(recent_gaps)
    )

    return {
        "recentMessages": [
            {
                "messageId": msg.message_id,
                "sessionId": msg.session_id,
                "tenantId": msg.tenant_id,
                "confidence": round(msg.answer_confidence, 3) if msg.answer_confidence is not None else None,
                "retrievalScore": round(msg.retrieval_score, 3) if msg.retrieval_score is not None else None,
                "responseTimeMs": msg.response_time_ms,
                "createdAt": msg.created_at.isoformat(),
                "hasIssues": (
                    (msg.answer_confidence is not None and msg.answer_confidence < 0.5) or
                    (msg.retrieval_score is not None and msg.retrieval_score < 0.5) or
                    (msg.response_time_ms is not None and msg.response_time_ms > 5000)
                )
            }
            for msg in recent_messages
        ],
        "recentFeedback": [
            {
                "id": fb.id,
                "messageId": fb.message_id,
                "tenantId": fb.tenant_id,
                "feedbackType": fb.feedback_type,
                "comment": fb.feedback_comment,
                "createdAt": fb.created_at.isoformat()
            }
            for fb in recent_feedback
        ],
        "recentKnowledgeGaps": [
            {
                "id": gap.id,
                "tenantId": gap.tenant_id,
                "questionPattern": gap.question_pattern[:100],
                "occurrenceCount": gap.occurrence_count,
                "status": gap.status,
                "detectedAt": gap.first_detected_at.isoformat()
            }
            for gap in recent_gaps
        ]
    }


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
            error=str(e))
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


# ============================================================================
# System Admin Cross-Tenant Quality Endpoints
# ============================================================================

@router.get("/quality/all-tenants")
async def get_all_tenants_quality(
    days: int = Query(default=7, ge=1, le=90, description="Days to analyze"),
    current_user: dict = Depends(require_system_admin),
    db: Session = Depends(get_db)
):
    """
    Get aggregate quality metrics across all tenants.

    Requires ROLE_SYSTEM_ADMIN.

    Returns:
        - Per-tenant quality summaries
        - Platform-wide averages
        - Tenant rankings by quality metrics
    """
    cutoff_date = datetime.now() - timedelta(days=days)

    logger.info(
        "System admin requesting all-tenants quality metrics",
        user_id=current_user.get("user_id"),
        days=days
    )

    # Get tenant-level aggregated metrics
    tenant_metrics = db.query(
        RAGQualityMetrics.tenant_id,
        func.count(RAGQualityMetrics.id).label('message_count'),
        func.avg(RAGQualityMetrics.answer_confidence).label('avg_confidence'),
        func.avg(RAGQualityMetrics.retrieval_score).label('avg_retrieval'),
        func.avg(RAGQualityMetrics.response_time_ms).label('avg_response_time'),
        func.count(func.nullif(RAGQualityMetrics.low_confidence_flag, False)).label('low_confidence_count')
    ).filter(
        RAGQualityMetrics.created_at >= cutoff_date
    ).group_by(RAGQualityMetrics.tenant_id).all()

    # Get feedback stats per tenant
    feedback_by_tenant = {}
    feedback_stats = db.query(
        AnswerFeedback.tenant_id,
        AnswerFeedback.feedback_type,
        func.count(AnswerFeedback.id).label('count')
    ).filter(
        AnswerFeedback.created_at >= cutoff_date
    ).group_by(AnswerFeedback.tenant_id, AnswerFeedback.feedback_type).all()

    for tenant_id, feedback_type, count in feedback_stats:
        if tenant_id not in feedback_by_tenant:
            feedback_by_tenant[tenant_id] = {'helpful': 0, 'not_helpful': 0}
        feedback_by_tenant[tenant_id][feedback_type] = count

    # Get knowledge gaps per tenant
    gaps_by_tenant = {}
    gap_stats = db.query(
        KnowledgeGap.tenant_id,
        func.count(KnowledgeGap.id).label('gap_count')
    ).filter(
        KnowledgeGap.status.in_(['detected', 'acknowledged'])
    ).group_by(KnowledgeGap.tenant_id).all()

    for tenant_id, gap_count in gap_stats:
        gaps_by_tenant[tenant_id] = gap_count

    # Build tenant summaries
    tenant_summaries = []
    platform_totals = {
        'total_messages': 0,
        'total_confidence': 0,
        'total_retrieval': 0,
        'total_response_time': 0,
        'tenant_count': 0
    }

    for metric in tenant_metrics:
        tenant_id = metric.tenant_id
        message_count = metric.message_count
        avg_confidence = round(metric.avg_confidence, 3) if metric.avg_confidence else 0
        avg_retrieval = round(metric.avg_retrieval, 3) if metric.avg_retrieval else 0
        avg_response_time = round(metric.avg_response_time, 0) if metric.avg_response_time else 0
        low_confidence_count = metric.low_confidence_count or 0

        feedback = feedback_by_tenant.get(tenant_id, {'helpful': 0, 'not_helpful': 0})
        total_feedback = feedback['helpful'] + feedback['not_helpful']
        helpful_percentage = round((feedback['helpful'] / total_feedback * 100), 1) if total_feedback > 0 else 0

        active_gaps = gaps_by_tenant.get(tenant_id, 0)

        tenant_summaries.append({
            'tenant_id': tenant_id,
            'message_count': message_count,
            'avg_confidence': avg_confidence,
            'avg_retrieval_score': avg_retrieval,
            'avg_response_time_ms': avg_response_time,
            'low_confidence_count': low_confidence_count,
            'low_confidence_percentage': round((low_confidence_count / message_count * 100), 1) if message_count > 0 else 0,
            'feedback': {
                'helpful': feedback['helpful'],
                'not_helpful': feedback['not_helpful'],
                'total': total_feedback,
                'helpful_percentage': helpful_percentage
            },
            'active_knowledge_gaps': active_gaps
        })

        # Update platform totals
        platform_totals['total_messages'] += message_count
        if metric.avg_confidence:
            platform_totals['total_confidence'] += metric.avg_confidence
        if metric.avg_retrieval:
            platform_totals['total_retrieval'] += metric.avg_retrieval
        if metric.avg_response_time:
            platform_totals['total_response_time'] += metric.avg_response_time
        platform_totals['tenant_count'] += 1

    # Calculate platform averages
    tenant_count = platform_totals['tenant_count']
    platform_averages = {
        'avg_confidence': round(platform_totals['total_confidence'] / tenant_count, 3) if tenant_count > 0 else 0,
        'avg_retrieval_score': round(platform_totals['total_retrieval'] / tenant_count, 3) if tenant_count > 0 else 0,
        'avg_response_time_ms': round(platform_totals['total_response_time'] / tenant_count, 0) if tenant_count > 0 else 0,
        'total_messages': platform_totals['total_messages'],
        'total_tenants': tenant_count
    }

    # Sort tenants by confidence score (descending)
    tenant_summaries.sort(key=lambda x: x['avg_confidence'], reverse=True)

    logger.info(
        "System admin retrieved all-tenants quality metrics",
        tenant_count=len(tenant_summaries),
        total_messages=platform_totals['total_messages']
    )

    return {
        'period': {
            'days': days,
            'start_date': cutoff_date.isoformat(),
            'end_date': datetime.now().isoformat()
        },
        'platform_summary': platform_averages,
        'tenants': tenant_summaries
    }


@router.get("/quality/tenant/{tenant_id}")
async def get_tenant_quality_details(
    tenant_id: str,
    days: int = Query(default=7, ge=1, le=90, description="Days to analyze"),
    current_user: dict = Depends(require_system_admin),
    db: Session = Depends(get_db)
):
    """
    Get detailed quality metrics for a specific tenant.

    Requires ROLE_SYSTEM_ADMIN.

    Returns:
        - Comprehensive quality metrics
        - Quality trends over time
        - Knowledge gaps
        - Recent low-quality messages
    """
    cutoff_date = datetime.now() - timedelta(days=days)

    logger.info(
        "System admin requesting tenant quality details",
        user_id=current_user.get("user_id"),
        tenant_id=tenant_id,
        days=days
    )

    # Overall metrics
    total_messages = db.query(func.count(RAGQualityMetrics.id)).filter(
        and_(
            RAGQualityMetrics.tenant_id == tenant_id,
            RAGQualityMetrics.created_at >= cutoff_date
        )
    ).scalar() or 0

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

    feedback_summary = {'helpful': 0, 'not_helpful': 0}
    for feedback_type, count in feedback_stats:
        feedback_summary[feedback_type] = count

    # Knowledge gaps
    active_gaps = db.query(KnowledgeGap).filter(
        and_(
            KnowledgeGap.tenant_id == tenant_id,
            KnowledgeGap.status.in_(['detected', 'acknowledged'])
        )
    ).order_by(desc(KnowledgeGap.occurrence_count)).limit(10).all()

    # Low quality messages (recent)
    low_quality_messages = db.query(RAGQualityMetrics).filter(
        and_(
            RAGQualityMetrics.tenant_id == tenant_id,
            RAGQualityMetrics.created_at >= cutoff_date,
            RAGQualityMetrics.answer_confidence < 0.5
        )
    ).order_by(desc(RAGQualityMetrics.created_at)).limit(20).all()

    # Daily trends
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

    trends = [
        {
            'date': metric.date.isoformat(),
            'message_count': metric.message_count,
            'avg_confidence': round(metric.avg_confidence, 3) if metric.avg_confidence else None,
            'avg_retrieval': round(metric.avg_retrieval, 3) if metric.avg_retrieval else None
        }
        for metric in daily_metrics
    ]

    logger.info(
        "System admin retrieved tenant quality details",
        tenant_id=tenant_id,
        total_messages=total_messages,
        active_gaps=len(active_gaps)
    )

    return {
        'tenant_id': tenant_id,
        'period': {
            'days': days,
            'start_date': cutoff_date.isoformat(),
            'end_date': datetime.now().isoformat()
        },
        'metrics': {
            'total_messages': total_messages,
            'avg_confidence': round(avg_stats.avg_confidence, 3) if avg_stats.avg_confidence else None,
            'avg_retrieval_score': round(avg_stats.avg_retrieval, 3) if avg_stats.avg_retrieval else None,
            'avg_response_time_ms': round(avg_stats.avg_response_time, 0) if avg_stats.avg_response_time else None
        },
        'feedback': {
            'helpful': feedback_summary['helpful'],
            'not_helpful': feedback_summary['not_helpful'],
            'total': sum(feedback_summary.values()),
            'helpful_percentage': round(
                (feedback_summary['helpful'] / sum(feedback_summary.values()) * 100), 1
            ) if sum(feedback_summary.values()) > 0 else 0
        },
        'knowledge_gaps': {
            'active_count': len(active_gaps),
            'top_gaps': [
                {
                    'id': gap.id,
                    'question_pattern': gap.question_pattern,
                    'occurrence_count': gap.occurrence_count,
                    'status': gap.status
                }
                for gap in active_gaps
            ]
        },
        'low_quality_messages': [
            {
                'message_id': msg.message_id,
                'session_id': msg.session_id,
                'confidence': round(msg.answer_confidence, 3),
                'retrieval_score': round(msg.retrieval_score, 3) if msg.retrieval_score else None,
                'created_at': msg.created_at.isoformat()
            }
            for msg in low_quality_messages
        ],
        'trends': trends
    }
