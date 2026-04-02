"""
Admin endpoints for agent session monitoring.

Provides super-admin access to view all agent sessions and messages
across tenants. Used by the super-admin dashboard.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..core.database import get_db
from ..models.agent_models import AgentSession, AgentMessage
from ..services.dependencies import TokenClaims, require_system_admin

router = APIRouter()


@router.get("/agent-sessions")
async def list_agent_sessions(
    page: int = Query(0, ge=0),
    size: int = Query(20, ge=1, le=100),
    service_key: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    tenant_id: Optional[str] = None,
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    """List all agent sessions across tenants (super-admin only)."""
    query = db.query(AgentSession)

    if service_key:
        query = query.filter(AgentSession.service_key == service_key)
    if status_filter:
        query = query.filter(AgentSession.status == status_filter)
    if tenant_id:
        query = query.filter(AgentSession.tenant_id == tenant_id)

    total = query.count()

    sessions = (
        query
        .order_by(AgentSession.last_activity.desc())
        .offset(page * size)
        .limit(size)
        .all()
    )

    items = []
    for s in sessions:
        msg_count = db.query(func.count(AgentMessage.id)).filter(
            AgentMessage.session_id == s.id
        ).scalar() or 0

        items.append({
            "id": s.id,
            "tenant_id": s.tenant_id,
            "user_id": s.user_id,
            "user_email": s.user_email,
            "user_full_name": s.user_full_name,
            "service_key": s.service_key,
            "status": s.status,
            "total_tokens_used": s.total_tokens_used or 0,
            "context_limit_tokens": s.context_limit_tokens,
            "model_name": s.model_name,
            "message_count": msg_count,
            "parent_session_id": s.parent_session_id,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "last_activity": s.last_activity.isoformat() if s.last_activity else None,
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
    }


@router.get("/agent-sessions/{session_id}")
async def get_agent_session_detail(
    session_id: str,
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    """Get full session detail with messages (super-admin only)."""
    session = db.query(AgentSession).filter(AgentSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    messages = (
        db.query(AgentMessage)
        .filter(AgentMessage.session_id == session_id)
        .order_by(AgentMessage.created_at)
        .all()
    )

    return {
        "session": {
            "id": session.id,
            "tenant_id": session.tenant_id,
            "user_id": session.user_id,
            "user_email": session.user_email,
            "user_full_name": session.user_full_name,
            "service_key": session.service_key,
            "status": session.status,
            "total_tokens_used": session.total_tokens_used or 0,
            "context_limit_tokens": session.context_limit_tokens,
            "model_name": session.model_name,
            "parent_session_id": session.parent_session_id,
            "context_summary": session.context_summary,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "last_activity": session.last_activity.isoformat() if session.last_activity else None,
        },
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "structured_blocks": m.structured_blocks,
                "token_count": m.token_count,
                "tool_calls": m.tool_calls,
                "message_metadata": m.message_metadata,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
    }
