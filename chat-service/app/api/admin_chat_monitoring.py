import json
import math
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, case, and_
from typing import List, Optional
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel
import io

from ..core.database import get_db
from ..models.chat_models import ChatSession, ChatMessage
from ..core.logging_config import get_logger
from ..services.dependencies import require_system_admin, TokenClaims
from ..services.tenant_client import TenantClient

router = APIRouter()
logger = get_logger("admin_chat_monitoring")

# ---- Response Models ----

class ChatMonitoringSession(BaseModel):
    id: str
    tenant_id: str
    tenant_name: Optional[str] = None
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    status: str
    message_count: int
    quality_score: Optional[float] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    last_message_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class MonitoringMessageResponse(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    timestamp: datetime
    metadata: Optional[dict] = None

    class Config:
        from_attributes = True


class SessionMessagesResponse(BaseModel):
    tenant_id: str
    tenant_name: Optional[str] = None
    messages: List[MonitoringMessageResponse]


class PageResponse(BaseModel):
    content: List[ChatMonitoringSession]
    totalElements: int
    totalPages: int
    size: int
    number: int
    first: bool
    last: bool
    empty: bool


# ---- Helpers ----

def _derive_status(is_active: bool, last_activity: Optional[datetime]) -> str:
    if not is_active:
        return "completed"
    if last_activity and last_activity > datetime.now(timezone.utc) - timedelta(minutes=30):
        return "active"
    return "abandoned"


def _map_message(msg: ChatMessage) -> MonitoringMessageResponse:
    role_map = {"user": "user", "assistant": "assistant", "system": "system"}
    return MonitoringMessageResponse(
        id=msg.id,
        session_id=msg.session_id,
        role=role_map.get(msg.message_type, msg.message_type),
        content=msg.content,
        timestamp=msg.created_at,
        metadata=msg.message_metadata if msg.message_metadata else None,
    )


# ---- Endpoints ----

@router.get("/sessions", response_model=PageResponse)
async def list_monitoring_sessions(
    page: int = Query(0, ge=0, description="Page number (0-based)"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
    tenantId: Optional[str] = Query(None, description="Filter by tenant ID"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status: active, completed, abandoned"),
    startDate: Optional[str] = Query(None, description="Filter sessions started after (ISO date)"),
    endDate: Optional[str] = Query(None, description="Filter sessions started before (ISO date)"),
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    """List chat sessions in Spring Data Page format for the superadmin UI."""
    logger.info("Chat monitoring sessions requested", user_id=claims.user_id, page=page, size=size)

    # Subquery for message counts
    msg_count_sq = (
        db.query(
            ChatMessage.session_id,
            func.count(ChatMessage.id).label("msg_count"),
        )
        .group_by(ChatMessage.session_id)
        .subquery()
    )

    query = (
        db.query(ChatSession, msg_count_sq.c.msg_count)
        .outerjoin(msg_count_sq, ChatSession.session_id == msg_count_sq.c.session_id)
    )

    # Filters
    if tenantId:
        query = query.filter(ChatSession.tenant_id == tenantId)

    if startDate:
        try:
            start_dt = datetime.fromisoformat(startDate.replace("Z", "+00:00"))
            query = query.filter(ChatSession.created_at >= start_dt)
        except ValueError:
            pass

    if endDate:
        try:
            end_dt = datetime.fromisoformat(endDate.replace("Z", "+00:00"))
            query = query.filter(ChatSession.created_at <= end_dt)
        except ValueError:
            pass

    # Status filter needs post-query logic since it's derived, but we can push some to SQL
    if status_filter == "completed":
        query = query.filter(ChatSession.is_active == False)
    elif status_filter == "active":
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
        query = query.filter(ChatSession.is_active == True, ChatSession.last_activity >= cutoff)
    elif status_filter == "abandoned":
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
        query = query.filter(
            ChatSession.is_active == True,
            (ChatSession.last_activity < cutoff) | (ChatSession.last_activity == None),
        )

    total = query.count()
    total_pages = math.ceil(total / size) if total > 0 else 0

    rows = (
        query.order_by(desc(ChatSession.last_activity))
        .offset(page * size)
        .limit(size)
        .all()
    )

    content = []
    for session, msg_count in rows:
        content.append(ChatMonitoringSession(
            id=session.session_id,
            tenant_id=session.tenant_id,
            user_id=session.user_identifier,
            user_email=session.auth_user_email,
            status=_derive_status(session.is_active, session.last_activity),
            message_count=msg_count or 0,
            quality_score=None,
            started_at=session.created_at,
            ended_at=None if session.is_active else session.last_activity,
            last_message_at=session.last_activity,
        ))

    return PageResponse(
        content=content,
        totalElements=total,
        totalPages=total_pages,
        size=size,
        number=page,
        first=(page == 0),
        last=(page >= total_pages - 1) if total_pages > 0 else True,
        empty=(len(content) == 0),
    )


@router.get("/sessions/{session_id}", response_model=ChatMonitoringSession)
async def get_monitoring_session(
    session_id: str,
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    """Get a single chat session detail."""
    session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    msg_count = db.query(func.count(ChatMessage.id)).filter(
        ChatMessage.session_id == session_id
    ).scalar()

    return ChatMonitoringSession(
        id=session.session_id,
        tenant_id=session.tenant_id,
        user_id=session.user_identifier,
        user_email=session.auth_user_email,
        status=_derive_status(session.is_active, session.last_activity),
        message_count=msg_count or 0,
        quality_score=None,
        started_at=session.created_at,
        ended_at=None if session.is_active else session.last_activity,
        last_message_at=session.last_activity,
    )


@router.get("/sessions/{session_id}/messages", response_model=SessionMessagesResponse)
async def get_monitoring_session_messages(
    session_id: str,
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    """Get messages for a session with role/timestamp mapping."""
    session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    tenant_client = TenantClient()
    tenant = await tenant_client.get_tenant_by_id(session.tenant_id)
    tenant_name = tenant.get("name") if tenant else None

    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
        .all()
    )

    return SessionMessagesResponse(
        tenant_id=session.tenant_id,
        tenant_name=tenant_name,
        messages=[_map_message(m) for m in messages],
    )


@router.get("/sessions/{session_id}/export")
async def export_monitoring_session(
    session_id: str,
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    """Export session and messages as a downloadable JSON file."""
    session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
        .all()
    )

    export_data = {
        "session": {
            "id": session.session_id,
            "tenant_id": session.tenant_id,
            "user_id": session.user_identifier,
            "user_email": session.auth_user_email,
            "status": _derive_status(session.is_active, session.last_activity),
            "is_active": session.is_active,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "last_activity": session.last_activity.isoformat() if session.last_activity else None,
        },
        "messages": [
            {
                "id": m.id,
                "role": {"user": "user", "assistant": "assistant", "system": "system"}.get(m.message_type, m.message_type),
                "content": m.content,
                "timestamp": m.created_at.isoformat() if m.created_at else None,
                "metadata": m.message_metadata,
            }
            for m in messages
        ],
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "message_count": len(messages),
    }

    json_bytes = json.dumps(export_data, indent=2, default=str).encode("utf-8")

    return StreamingResponse(
        io.BytesIO(json_bytes),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="session-{session_id}.json"',
        },
    )
