"""
Alerts & Scheduler API

Endpoints for managing alert rules, viewing alert history, and monitoring scheduled jobs.
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
from typing import List, Optional
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.core.auth import validate_token, require_admin
from app.core.config import settings
from app.models.alert_rule import AlertRule
from app.models.alert_history import AlertHistory
from app.models.job_log import JobExecutionLog
from app.services.alert_manager import AlertManager
from app.services.notification_client import notification_client
from app.services.scheduler import background_scheduler
from app.core.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter()


# ==================== Request/Response Schemas ====================

class AlertRuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    rule_type: str = Field(..., pattern="^(quality_drop|new_gaps|high_negative_feedback|session_degradation)$")
    description: Optional[str] = None
    threshold_value: float
    check_interval_hours: int = Field(default=24, ge=1, le=168)
    min_sample_size: int = Field(default=10, ge=1)
    notification_channels: List[str]
    notification_recipients: Optional[dict] = None
    throttle_minutes: int = Field(default=1440, ge=60)
    enabled: bool = True


class AlertRuleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    threshold_value: Optional[float] = None
    check_interval_hours: Optional[int] = Field(None, ge=1, le=168)
    min_sample_size: Optional[int] = Field(None, ge=1)
    notification_channels: Optional[List[str]] = None
    notification_recipients: Optional[dict] = None
    throttle_minutes: Optional[int] = Field(None, ge=60)
    enabled: Optional[bool] = None


class TestAlertRequest(BaseModel):
    rule_id: Optional[str] = None
    channels: Optional[List[str]] = None
    recipients: Optional[dict] = None


# ==================== Alert Rules Endpoints ====================

@router.post("/rules", status_code=status.HTTP_201_CREATED)
async def create_alert_rule(
    rule_data: AlertRuleCreate,
    current_user: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Create a new alert rule.

    Requires admin role.
    """
    tenant_id = current_user["tenant_id"]

    # Create rule
    rule = AlertRule(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        name=rule_data.name,
        rule_type=rule_data.rule_type,
        description=rule_data.description,
        threshold_value=rule_data.threshold_value,
        check_interval_hours=rule_data.check_interval_hours,
        min_sample_size=rule_data.min_sample_size,
        notification_channels=rule_data.notification_channels,
        notification_recipients=rule_data.notification_recipients,
        throttle_minutes=rule_data.throttle_minutes,
        enabled=rule_data.enabled,
        created_by=current_user.get("user_id")
    )

    db.add(rule)
    db.commit()
    db.refresh(rule)

    logger.info(
        "Alert rule created",
        tenant_id=tenant_id,
        rule_id=rule.id,
        rule_name=rule.name,
        rule_type=rule.rule_type
    )

    return {
        "id": rule.id,
        "name": rule.name,
        "rule_type": rule.rule_type,
        "enabled": rule.enabled,
        "created_at": rule.created_at.isoformat()
    }


@router.get("/rules")
async def list_alert_rules(
    enabled_only: bool = Query(default=False),
    current_user: dict = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """
    List all alert rules for the tenant.

    Requires authentication.
    """
    tenant_id = current_user["tenant_id"]

    query = db.query(AlertRule).filter(AlertRule.tenant_id == tenant_id)

    if enabled_only:
        query = query.filter(AlertRule.enabled == True)

    rules = query.order_by(desc(AlertRule.created_at)).all()

    return {
        "count": len(rules),
        "rules": [
            {
                "id": rule.id,
                "name": rule.name,
                "rule_type": rule.rule_type,
                "description": rule.description,
                "threshold_value": rule.threshold_value,
                "check_interval_hours": rule.check_interval_hours,
                "min_sample_size": rule.min_sample_size,
                "notification_channels": rule.notification_channels,
                "throttle_minutes": rule.throttle_minutes,
                "enabled": rule.enabled,
                "last_triggered_at": rule.last_triggered_at.isoformat() if rule.last_triggered_at else None,
                "created_at": rule.created_at.isoformat()
            }
            for rule in rules
        ]
    }


@router.get("/rules/{rule_id}")
async def get_alert_rule(
    rule_id: str,
    current_user: dict = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """
    Get a specific alert rule.

    Requires authentication.
    """
    tenant_id = current_user["tenant_id"]

    rule = db.query(AlertRule).filter(
        and_(
            AlertRule.id == rule_id,
            AlertRule.tenant_id == tenant_id
        )
    ).first()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert rule not found"
        )

    return {
        "id": rule.id,
        "name": rule.name,
        "rule_type": rule.rule_type,
        "description": rule.description,
        "threshold_value": rule.threshold_value,
        "check_interval_hours": rule.check_interval_hours,
        "min_sample_size": rule.min_sample_size,
        "notification_channels": rule.notification_channels,
        "notification_recipients": rule.notification_recipients,
        "throttle_minutes": rule.throttle_minutes,
        "enabled": rule.enabled,
        "last_triggered_at": rule.last_triggered_at.isoformat() if rule.last_triggered_at else None,
        "created_at": rule.created_at.isoformat(),
        "updated_at": rule.updated_at.isoformat(),
        "created_by": rule.created_by
    }


@router.put("/rules/{rule_id}")
async def update_alert_rule(
    rule_id: str,
    rule_data: AlertRuleUpdate,
    current_user: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Update an alert rule.

    Requires admin role.
    """
    tenant_id = current_user["tenant_id"]

    rule = db.query(AlertRule).filter(
        and_(
            AlertRule.id == rule_id,
            AlertRule.tenant_id == tenant_id
        )
    ).first()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert rule not found"
        )

    # Update fields
    update_data = rule_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(rule, field, value)

    db.commit()
    db.refresh(rule)

    logger.info(
        "Alert rule updated",
        tenant_id=tenant_id,
        rule_id=rule.id,
        rule_name=rule.name
    )

    return {
        "id": rule.id,
        "name": rule.name,
        "enabled": rule.enabled,
        "updated_at": rule.updated_at.isoformat()
    }


@router.delete("/rules/{rule_id}")
async def delete_alert_rule(
    rule_id: str,
    current_user: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Delete an alert rule.

    Requires admin role.
    """
    tenant_id = current_user["tenant_id"]

    rule = db.query(AlertRule).filter(
        and_(
            AlertRule.id == rule_id,
            AlertRule.tenant_id == tenant_id
        )
    ).first()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert rule not found"
        )

    db.delete(rule)
    db.commit()

    logger.info(
        "Alert rule deleted",
        tenant_id=tenant_id,
        rule_id=rule_id
    )

    return {"success": True, "rule_id": rule_id}


# ==================== Alert History Endpoints ====================

@router.get("/history")
async def get_alert_history(
    rule_id: Optional[str] = None,
    severity: Optional[str] = Query(None, regex="^(info|warning|critical)$"),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: dict = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """
    Get alert history for the tenant.

    Requires authentication.
    """
    tenant_id = current_user["tenant_id"]

    query = db.query(AlertHistory).filter(AlertHistory.tenant_id == tenant_id)

    if rule_id:
        query = query.filter(AlertHistory.rule_id == rule_id)

    if severity:
        query = query.filter(AlertHistory.severity == severity)

    alerts = query.order_by(desc(AlertHistory.triggered_at)).limit(limit).all()

    return {
        "count": len(alerts),
        "alerts": [
            {
                "id": alert.id,
                "rule_id": alert.rule_id,
                "rule_name": alert.rule_name,
                "rule_type": alert.rule_type,
                "severity": alert.severity,
                "message": alert.alert_message,
                "data": alert.alert_data,
                "notification_sent": alert.notification_sent,
                "triggered_at": alert.triggered_at.isoformat(),
                "processed_at": alert.processed_at.isoformat() if alert.processed_at else None
            }
            for alert in alerts
        ]
    }


# ==================== Testing & Utilities ====================

@router.post("/test")
async def test_alert(
    test_data: TestAlertRequest,
    current_user: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Send a test alert notification.

    Requires admin role.
    """
    tenant_id = current_user["tenant_id"]

    # Prepare test alert data
    alert_data = {
        "rule_name": "Test Alert",
        "rule_type": "test",
        "severity": "info",
        "message": "This is a test alert from the Answer Quality & Feedback Service.",
        "triggered_at": datetime.now().isoformat(),
        "current_value": 0.0,
        "threshold": 0.0
    }

    # Use specified channels or default
    channels = test_data.channels or ["console"]

    # Use specified recipients or None
    recipients = test_data.recipients

    # Send notification
    try:
        results = await notification_client.send_notification(
            tenant_id=tenant_id,
            alert_data=alert_data,
            channels=channels,
            recipients=recipients
        )

        logger.info(
            "Test alert sent",
            tenant_id=tenant_id,
            channels=channels,
            results=results
        )

        return {
            "success": True,
            "channels": channels,
            "results": results
        }

    except Exception as e:
        logger.exception(
            f"Test alert failed: {e}",
            tenant_id=tenant_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send test alert: {str(e)}"
        )


@router.post("/check-now")
async def check_alerts_now(
    current_user: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Manually trigger alert checking for the tenant.

    Requires admin role.
    """
    tenant_id = current_user["tenant_id"]

    logger.info(
        "Manual alert check triggered",
        tenant_id=tenant_id,
        user_id=current_user.get("user_id")
    )

    try:
        alert_manager = AlertManager(db)
        result = await alert_manager.check_all_rules(tenant_id=tenant_id)

        return {
            "success": True,
            "result": result
        }

    except Exception as e:
        logger.exception(
            f"Manual alert check failed: {e}",
            tenant_id=tenant_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check alerts: {str(e)}"
        )


# ==================== Scheduler Status ====================

@router.get("/scheduler/status")
async def get_scheduler_status(
    current_user: dict = Depends(validate_token)
):
    """
    Get scheduler status and job information.

    Requires authentication.
    """
    return background_scheduler.get_job_status()


@router.get("/jobs/logs")
async def get_job_logs(
    job_type: Optional[str] = None,
    status_filter: Optional[str] = Query(None, regex="^(success|failed|partial)$"),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: dict = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """
    Get execution logs for scheduled jobs.

    Requires authentication.
    """
    tenant_id = current_user["tenant_id"]

    query = db.query(JobExecutionLog).filter(
        (JobExecutionLog.tenant_id == tenant_id) | (JobExecutionLog.tenant_id.is_(None))
    )

    if job_type:
        query = query.filter(JobExecutionLog.job_type == job_type)

    if status_filter:
        query = query.filter(JobExecutionLog.status == status_filter)

    logs = query.order_by(desc(JobExecutionLog.started_at)).limit(limit).all()

    return {
        "count": len(logs),
        "logs": [
            {
                "id": log.id,
                "job_name": log.job_name,
                "job_type": log.job_type,
                "status": log.status,
                "started_at": log.started_at.isoformat(),
                "completed_at": log.completed_at.isoformat() if log.completed_at else None,
                "duration_ms": log.duration_ms,
                "result_summary": log.result_summary,
                "error_message": log.error_message,
                "triggered_by": log.triggered_by
            }
            for log in logs
        ]
    }


# Import datetime for test alert
from datetime import datetime
