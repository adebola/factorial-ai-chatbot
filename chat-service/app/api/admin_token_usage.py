"""Admin endpoints for token usage monitoring."""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, cast, Date
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.logging_config import get_logger
from ..models.chat_models import TokenUsage
from ..services.dependencies import require_system_admin, require_admin, TokenClaims

router = APIRouter()
logger = get_logger("admin_token_usage")


def _parse_dates(start_date: Optional[str], end_date: Optional[str]):
    """Parse date strings to datetime objects with defaults."""
    end = datetime.utcnow()
    start = end - timedelta(days=30)
    if start_date:
        start = datetime.fromisoformat(start_date)
    if end_date:
        end = datetime.fromisoformat(end_date)
    return start, end


@router.get("/admin/token-usage/summary")
async def get_token_usage_summary(
    tenant_id: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    """Aggregated token usage totals (system admin only)."""
    start, end = _parse_dates(start_date, end_date)
    query = db.query(
        func.coalesce(func.sum(TokenUsage.prompt_tokens), 0).label("total_prompt_tokens"),
        func.coalesce(func.sum(TokenUsage.completion_tokens), 0).label("total_completion_tokens"),
        func.coalesce(func.sum(TokenUsage.total_tokens), 0).label("total_tokens"),
        func.coalesce(func.sum(TokenUsage.estimated_cost_usd), 0.0).label("total_cost_usd"),
        func.count(TokenUsage.id).label("request_count"),
    ).filter(TokenUsage.created_at.between(start, end))

    if tenant_id:
        query = query.filter(TokenUsage.tenant_id == tenant_id)

    row = query.one()
    return {
        "total_prompt_tokens": int(row.total_prompt_tokens),
        "total_completion_tokens": int(row.total_completion_tokens),
        "total_tokens": int(row.total_tokens),
        "total_cost_usd": float(row.total_cost_usd),
        "request_count": int(row.request_count),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "service": "chat",
    }


@router.get("/admin/token-usage/by-tenant")
async def get_token_usage_by_tenant(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    page: int = Query(0, ge=0),
    size: int = Query(20, ge=1, le=100),
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    """Per-tenant token usage breakdown (system admin only)."""
    start, end = _parse_dates(start_date, end_date)
    query = (
        db.query(
            TokenUsage.tenant_id,
            func.sum(TokenUsage.prompt_tokens).label("total_prompt_tokens"),
            func.sum(TokenUsage.completion_tokens).label("total_completion_tokens"),
            func.sum(TokenUsage.total_tokens).label("total_tokens"),
            func.sum(TokenUsage.estimated_cost_usd).label("total_cost_usd"),
            func.count(TokenUsage.id).label("request_count"),
        )
        .filter(TokenUsage.created_at.between(start, end))
        .group_by(TokenUsage.tenant_id)
        .order_by(func.sum(TokenUsage.estimated_cost_usd).desc())
    )

    total = query.count()
    rows = query.offset(page * size).limit(size).all()

    return {
        "items": [
            {
                "tenant_id": r.tenant_id,
                "total_prompt_tokens": int(r.total_prompt_tokens),
                "total_completion_tokens": int(r.total_completion_tokens),
                "total_tokens": int(r.total_tokens),
                "total_cost_usd": float(r.total_cost_usd),
                "request_count": int(r.request_count),
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "size": size,
        "service": "chat",
    }


@router.get("/admin/token-usage/daily")
async def get_daily_token_usage(
    tenant_id: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    """Daily token usage time series (system admin only)."""
    start, end = _parse_dates(start_date, end_date)
    date_col = cast(TokenUsage.created_at, Date)
    query = (
        db.query(
            date_col.label("date"),
            func.sum(TokenUsage.prompt_tokens).label("prompt_tokens"),
            func.sum(TokenUsage.completion_tokens).label("completion_tokens"),
            func.sum(TokenUsage.total_tokens).label("total_tokens"),
            func.sum(TokenUsage.estimated_cost_usd).label("cost_usd"),
            func.count(TokenUsage.id).label("request_count"),
        )
        .filter(TokenUsage.created_at.between(start, end))
        .group_by(date_col)
        .order_by(date_col)
    )

    if tenant_id:
        query = query.filter(TokenUsage.tenant_id == tenant_id)

    rows = query.all()
    return {
        "items": [
            {
                "date": str(r.date),
                "prompt_tokens": int(r.prompt_tokens),
                "completion_tokens": int(r.completion_tokens),
                "total_tokens": int(r.total_tokens),
                "cost_usd": float(r.cost_usd),
                "request_count": int(r.request_count),
            }
            for r in rows
        ],
        "service": "chat",
    }


@router.get("/admin/token-usage/by-model")
async def get_token_usage_by_model(
    tenant_id: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    """Per-model token usage breakdown (system admin only)."""
    start, end = _parse_dates(start_date, end_date)
    query = (
        db.query(
            TokenUsage.model,
            TokenUsage.usage_type,
            func.sum(TokenUsage.prompt_tokens).label("total_prompt_tokens"),
            func.sum(TokenUsage.completion_tokens).label("total_completion_tokens"),
            func.sum(TokenUsage.total_tokens).label("total_tokens"),
            func.sum(TokenUsage.estimated_cost_usd).label("total_cost_usd"),
            func.count(TokenUsage.id).label("request_count"),
        )
        .filter(TokenUsage.created_at.between(start, end))
        .group_by(TokenUsage.model, TokenUsage.usage_type)
        .order_by(func.sum(TokenUsage.estimated_cost_usd).desc())
    )

    if tenant_id:
        query = query.filter(TokenUsage.tenant_id == tenant_id)

    rows = query.all()
    return {
        "items": [
            {
                "model": r.model,
                "usage_type": r.usage_type,
                "total_prompt_tokens": int(r.total_prompt_tokens),
                "total_completion_tokens": int(r.total_completion_tokens),
                "total_tokens": int(r.total_tokens),
                "total_cost_usd": float(r.total_cost_usd),
                "request_count": int(r.request_count),
            }
            for r in rows
        ],
        "service": "chat",
    }


@router.get("/admin/token-usage/records")
async def get_token_usage_records(
    tenant_id: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    page: int = Query(0, ge=0),
    size: int = Query(20, ge=1, le=100),
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    """Raw token usage records (system admin only)."""
    start, end = _parse_dates(start_date, end_date)
    query = db.query(TokenUsage).filter(TokenUsage.created_at.between(start, end))

    if tenant_id:
        query = query.filter(TokenUsage.tenant_id == tenant_id)

    total = query.count()
    records = query.order_by(TokenUsage.created_at.desc()).offset(page * size).limit(size).all()

    return {
        "items": [
            {
                "id": r.id,
                "tenant_id": r.tenant_id,
                "session_id": r.session_id,
                "model": r.model,
                "usage_type": r.usage_type,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "total_tokens": r.total_tokens,
                "estimated_cost_usd": r.estimated_cost_usd,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ],
        "total": total,
        "page": page,
        "size": size,
        "service": "chat",
    }


@router.get("/tenant/token-usage/summary")
async def get_tenant_token_usage_summary(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    claims: TokenClaims = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Token usage summary for the current tenant (tenant admin only)."""
    start, end = _parse_dates(start_date, end_date)
    row = (
        db.query(
            func.coalesce(func.sum(TokenUsage.prompt_tokens), 0).label("total_prompt_tokens"),
            func.coalesce(func.sum(TokenUsage.completion_tokens), 0).label("total_completion_tokens"),
            func.coalesce(func.sum(TokenUsage.total_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(TokenUsage.estimated_cost_usd), 0.0).label("total_cost_usd"),
            func.count(TokenUsage.id).label("request_count"),
        )
        .filter(
            TokenUsage.tenant_id == claims.tenant_id,
            TokenUsage.created_at.between(start, end),
        )
        .one()
    )

    return {
        "tenant_id": claims.tenant_id,
        "total_prompt_tokens": int(row.total_prompt_tokens),
        "total_completion_tokens": int(row.total_completion_tokens),
        "total_tokens": int(row.total_tokens),
        "total_cost_usd": float(row.total_cost_usd),
        "request_count": int(row.request_count),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "service": "chat",
    }
