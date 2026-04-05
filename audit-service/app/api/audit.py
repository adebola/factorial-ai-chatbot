"""Audit event query API. Super-admin only."""
import csv
import io
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models.audit_event import AuditEvent
from ..schemas.audit_event import AuditEventResponse, AuditEventListResponse, AuditStatsResponse
from ..services.dependencies import TokenClaims, validate_token, require_system_admin

router = APIRouter()


@router.get("/events", response_model=AuditEventListResponse)
async def list_audit_events(
    page: int = Query(0, ge=0),
    size: int = Query(20, ge=1, le=100),
    tenant_id: Optional[str] = None,
    actor_user_id: Optional[str] = None,
    action_type: Optional[str] = None,
    tier: Optional[str] = None,
    resource_type: Optional[str] = None,
    source_service: Optional[str] = None,
    trace_id: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    """List audit events with filtering and pagination."""
    query = db.query(AuditEvent)

    if tenant_id:
        query = query.filter(AuditEvent.tenant_id == tenant_id)
    if actor_user_id:
        query = query.filter(AuditEvent.actor_user_id == actor_user_id)
    if action_type:
        query = query.filter(AuditEvent.action_type == action_type)
    if tier:
        query = query.filter(AuditEvent.tier == tier)
    if resource_type:
        query = query.filter(AuditEvent.resource_type == resource_type)
    if source_service:
        query = query.filter(AuditEvent.source_service == source_service)
    if trace_id:
        query = query.filter(AuditEvent.trace_id == trace_id)
    if date_from:
        query = query.filter(AuditEvent.occurred_at >= date_from)
    if date_to:
        query = query.filter(AuditEvent.occurred_at <= date_to)

    total = query.count()
    events = (
        query
        .order_by(AuditEvent.occurred_at.desc())
        .offset(page * size)
        .limit(size)
        .all()
    )

    return AuditEventListResponse(
        items=[AuditEventResponse.from_orm(e) for e in events],
        total=total,
        page=page,
        size=size,
    )


@router.get("/events/export")
async def export_audit_events(
    tenant_id: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    format: str = Query("csv", pattern="^(csv|json)$"),
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    """Export audit events as CSV or JSON for compliance."""
    query = db.query(AuditEvent)
    if tenant_id:
        query = query.filter(AuditEvent.tenant_id == tenant_id)
    if date_from:
        query = query.filter(AuditEvent.occurred_at >= date_from)
    if date_to:
        query = query.filter(AuditEvent.occurred_at <= date_to)

    events = query.order_by(AuditEvent.occurred_at.desc()).limit(10000).all()

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "event_id", "tenant_id", "actor_email", "actor_type",
            "action_type", "tier", "resource_type", "resource_id",
            "source_service", "trace_id", "occurred_at"
        ])
        for e in events:
            writer.writerow([
                e.event_id, e.tenant_id, e.actor_email, e.actor_type,
                e.action_type, e.tier, e.resource_type, e.resource_id,
                e.source_service, e.trace_id,
                e.occurred_at.isoformat() if e.occurred_at else ""
            ])
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode()),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=audit-export.csv"}
        )
    else:
        import json
        items = [AuditEventResponse.from_orm(e).dict() for e in events]
        return StreamingResponse(
            io.BytesIO(json.dumps(items, default=str, indent=2).encode()),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=audit-export.json"}
        )


@router.get("/events/{event_id}", response_model=AuditEventResponse)
async def get_audit_event(
    event_id: str,
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    """Get a single audit event by ID."""
    event = db.query(AuditEvent).filter(AuditEvent.event_id == event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return AuditEventResponse.from_orm(event)


@router.get("/stats", response_model=AuditStatsResponse)
async def get_audit_stats(
    tenant_id: Optional[str] = None,
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    """Get aggregated audit statistics."""
    base_query = db.query(AuditEvent)
    if tenant_id:
        base_query = base_query.filter(AuditEvent.tenant_id == tenant_id)

    total = base_query.count()

    by_tier = dict(
        base_query.with_entities(AuditEvent.tier, func.count(AuditEvent.id))
        .group_by(AuditEvent.tier).all()
    )
    by_service = dict(
        base_query.with_entities(AuditEvent.source_service, func.count(AuditEvent.id))
        .group_by(AuditEvent.source_service).all()
    )
    by_action = dict(
        base_query.with_entities(AuditEvent.action_type, func.count(AuditEvent.id))
        .group_by(AuditEvent.action_type).order_by(func.count(AuditEvent.id).desc())
        .limit(20).all()
    )

    return AuditStatsResponse(
        total_events=total,
        by_tier=by_tier,
        by_service=by_service,
        by_action_type=by_action,
    )


# ═══════════════════════════════════════════════════════════
# TENANT-SCOPED ENDPOINTS (any authenticated user, own tenant only)
# ═══════════════════════════════════════════════════════════

@router.get("/tenant/events", response_model=AuditEventListResponse)
async def list_tenant_audit_events(
    page: int = Query(0, ge=0),
    size: int = Query(20, ge=1, le=100),
    action_type: Optional[str] = None,
    tier: Optional[str] = None,
    resource_type: Optional[str] = None,
    source_service: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db),
):
    """List audit events for the authenticated user's tenant."""
    query = db.query(AuditEvent).filter(AuditEvent.tenant_id == claims.tenant_id)

    if action_type:
        query = query.filter(AuditEvent.action_type == action_type)
    if tier:
        query = query.filter(AuditEvent.tier == tier)
    if resource_type:
        query = query.filter(AuditEvent.resource_type == resource_type)
    if source_service:
        query = query.filter(AuditEvent.source_service == source_service)
    if date_from:
        query = query.filter(AuditEvent.occurred_at >= date_from)
    if date_to:
        query = query.filter(AuditEvent.occurred_at <= date_to)

    total = query.count()
    events = (
        query
        .order_by(AuditEvent.occurred_at.desc())
        .offset(page * size)
        .limit(size)
        .all()
    )

    return AuditEventListResponse(
        items=[AuditEventResponse.from_orm(e) for e in events],
        total=total,
        page=page,
        size=size,
    )


@router.get("/tenant/stats", response_model=AuditStatsResponse)
async def get_tenant_audit_stats(
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db),
):
    """Get audit statistics for the authenticated user's tenant."""
    base_query = db.query(AuditEvent).filter(AuditEvent.tenant_id == claims.tenant_id)

    total = base_query.count()
    by_tier = dict(
        base_query.with_entities(AuditEvent.tier, func.count(AuditEvent.id))
        .group_by(AuditEvent.tier).all()
    )
    by_service = dict(
        base_query.with_entities(AuditEvent.source_service, func.count(AuditEvent.id))
        .group_by(AuditEvent.source_service).all()
    )
    by_action = dict(
        base_query.with_entities(AuditEvent.action_type, func.count(AuditEvent.id))
        .group_by(AuditEvent.action_type).order_by(func.count(AuditEvent.id).desc())
        .limit(20).all()
    )

    return AuditStatsResponse(
        total_events=total,
        by_tier=by_tier,
        by_service=by_service,
        by_action_type=by_action,
    )
