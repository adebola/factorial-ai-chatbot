from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field

from ..core.database import get_db
from ..models.chat_models import ChatSession, ChatMessage
from ..core.logging_config import get_logger
from ..services.dependencies import validate_token, require_system_admin, require_admin, TokenClaims

router = APIRouter()
logger = get_logger("chat")

# Response models
class ChatMessageResponse(BaseModel):
    id: str
    session_id: str
    message_type: str
    content: str
    message_metadata: dict
    created_at: datetime

    class Config:
        from_attributes = True


class ChatSessionResponse(BaseModel):
    id: str
    session_id: str
    user_identifier: Optional[str]
    is_active: bool
    created_at: datetime
    last_activity: Optional[datetime]
    message_count: int

    class Config:
        from_attributes = True


class ChatSessionWithMessagesResponse(BaseModel):
    session: ChatSessionResponse
    messages: List[ChatMessageResponse]

    class Config:
        from_attributes = True


# Security scheme for Bearer token
security = HTTPBearer()

@router.get("/admin/sessions", response_model=List[ChatSessionResponse])
async def list_chat_sessions(
    limit: int = Query(50, ge=1, le=500, description="Number of sessions to return"),
    offset: int = Query(0, ge=0, description="Number of sessions to skip"),
    active_only: bool = Query(False, description="Return only active sessions"),
    tenant_id: Optional[str] = Query(None, description="Filter by tenant ID (system admin only)"),
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db)
):
    """List all chat sessions (system admin only - cross-tenant)"""

    logger.info("System admin listing chat sessions", user_id=claims.user_id, limit=limit, offset=offset, tenant_id=tenant_id)

    # Build query - system admins can query all tenants or filter by specific tenant
    query = db.query(ChatSession)

    if tenant_id:
        query = query.filter(ChatSession.tenant_id == tenant_id)

    if active_only:
        query = query.filter(ChatSession.is_active == True)
    
    # Get sessions with message count
    sessions = query.order_by(desc(ChatSession.last_activity)).offset(offset).limit(limit).all()

    # Add a message count to each session
    session_responses = []
    for session in sessions:
        message_count = db.query(ChatMessage).filter(
            ChatMessage.session_id == session.session_id
        ).count()
        
        session_response = ChatSessionResponse(
            id=session.id,
            session_id=session.session_id,
            user_identifier=session.user_identifier,
            is_active=session.is_active,
            created_at=session.created_at,
            last_activity=session.last_activity,
            message_count=message_count
        )
        session_responses.append(session_response)

    logger.info("System admin retrieved chat sessions", count=len(session_responses), filtered_tenant=tenant_id)
    return session_responses


@router.get("/admin/sessions/{session_id}/messages", response_model=List[ChatMessageResponse])
async def get_session_messages(
    session_id: str,
    limit: int = Query(100, ge=1, le=1000, description="Number of messages to return"),
    offset: int = Query(0, ge=0, description="Number of messages to skip"),
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db)
):
    """Get all messages for a specific chat session (system admin only)"""

    logger.info("System admin getting session messages", user_id=claims.user_id, session_id=session_id)

    # Verify session exists (no tenant filtering for system admin)
    session = db.query(ChatSession).filter(
        ChatSession.session_id == session_id
    ).first()

    if not session:
        logger.warning("Session not found", session_id=session_id)
        raise HTTPException(status_code=404, detail="Session not found")

    # Get messages for the session
    messages = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).order_by(ChatMessage.created_at).offset(offset).limit(limit).all()

    logger.info("System admin retrieved session messages",
               session_id=session_id,
               count=len(messages))

    return [ChatMessageResponse.from_orm(message) for message in messages]


@router.get("/admin/sessions/{session_id}", response_model=ChatSessionWithMessagesResponse)
async def get_session_with_messages(
    session_id: str,
    message_limit: int = Query(100, ge=1, le=1000, description="Number of messages to return"),
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db)
):
    """Get a complete chat session with all messages (system admin only)"""

    logger.info("System admin getting complete session", user_id=claims.user_id, session_id=session_id)

    # Get session (no tenant filtering for system admin)
    session = db.query(ChatSession).filter(
        ChatSession.session_id == session_id
    ).first()

    if not session:
        logger.warning("Session not found", session_id=session_id)
        raise HTTPException(status_code=404, detail="Session not found")

    # Get messages for the session
    messages = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).order_by(ChatMessage.created_at).limit(message_limit).all()

    # Get message count
    message_count = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).count()
    
    # Build response
    session_response = ChatSessionResponse(
        id=session.id,
        session_id=session.session_id,
        user_identifier=session.user_identifier,
        is_active=session.is_active,
        created_at=session.created_at,
        last_activity=session.last_activity,
        message_count=message_count
    )
    
    message_responses = [ChatMessageResponse.from_orm(message) for message in messages]

    logger.info("System admin retrieved complete session",
               session_id=session_id,
               message_count=len(message_responses))

    return ChatSessionWithMessagesResponse(
        session=session_response,
        messages=message_responses
    )


@router.get("/admin/messages/search")
async def search_messages(
    query: str = Query(..., description="Search query for message content"),
    limit: int = Query(50, ge=1, le=500, description="Number of messages to return"),
    offset: int = Query(0, ge=0, description="Number of messages to skip"),
    message_type: Optional[str] = Query(None, description="Filter by message type (user/assistant)"),
    session_id: Optional[str] = Query(None, description="Filter by specific session"),
    tenant_id: Optional[str] = Query(None, description="Filter by tenant ID (system admin only)"),
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db)
):
    """Search messages by content (system admin only - cross-tenant)"""

    logger.info("System admin searching messages",
               user_id=claims.user_id,
               query=query,
               message_type=message_type,
               session_id=session_id,
               tenant_id=tenant_id)

    # Build search query
    search_query = db.query(ChatMessage).filter(
        ChatMessage.content.ilike(f"%{query}%")
    )

    # Optional tenant filter
    if tenant_id:
        search_query = search_query.filter(ChatMessage.tenant_id == tenant_id)
    
    # Apply filters
    if message_type:
        search_query = search_query.filter(ChatMessage.message_type == message_type)
    
    if session_id:
        search_query = search_query.filter(ChatMessage.session_id == session_id)
    
    # Execute query
    messages = search_query.order_by(desc(ChatMessage.created_at)).offset(offset).limit(limit).all()

    logger.info("System admin message search results",
               query=query,
               count=len(messages),
               filtered_tenant=tenant_id)

    return [ChatMessageResponse.from_orm(message) for message in messages]


@router.get("/admin/stats")
async def get_chat_stats(
    tenant_id: Optional[str] = Query(None, description="Filter by tenant ID (system admin only)"),
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db)
):
    """Get chat statistics (system admin only - cross-tenant or filtered by tenant)"""

    logger.info("System admin getting chat stats", user_id=claims.user_id, tenant_id=tenant_id)

    # Build base queries - can be filtered by tenant or system-wide
    session_query = db.query(ChatSession)
    message_query = db.query(ChatMessage)

    if tenant_id:
        session_query = session_query.filter(ChatSession.tenant_id == tenant_id)
        message_query = message_query.filter(ChatMessage.tenant_id == tenant_id)

    # Get various stats
    total_sessions = session_query.count()
    active_sessions = session_query.filter(ChatSession.is_active == True).count()

    total_messages = message_query.count()
    user_messages = message_query.filter(ChatMessage.message_type == "user").count()
    assistant_messages = message_query.filter(ChatMessage.message_type == "assistant").count()

    # Get recent activity (last 24 hours)
    from datetime import timedelta
    yesterday = datetime.utcnow() - timedelta(days=1)
    recent_messages = message_query.filter(ChatMessage.created_at >= yesterday).count()

    stats = {
        "total_sessions": total_sessions,
        "active_sessions": active_sessions,
        "total_messages": total_messages,
        "user_messages": user_messages,
        "assistant_messages": assistant_messages,
        "recent_messages_24h": recent_messages,
        "tenant_id": tenant_id if tenant_id else "all_tenants"
    }

    logger.info("System admin retrieved chat stats", stats=stats, filtered_tenant=tenant_id)
    return stats


# ============================================================================
# TENANT ADMIN ROUTES (ROLE_TENANT_ADMIN)
# These routes are automatically scoped to the authenticated tenant's data
# Tenant admins cannot access other tenants' data
# ============================================================================

@router.get("/tenant/sessions", response_model=List[ChatSessionResponse])
async def list_tenant_chat_sessions(
    limit: int = Query(50, ge=1, le=500, description="Number of sessions to return"),
    offset: int = Query(0, ge=0, description="Number of sessions to skip"),
    active_only: bool = Query(False, description="Filter for active sessions only"),
    claims: TokenClaims = Depends(require_admin),  # TENANT_ADMIN only
    db: Session = Depends(get_db)
):
    """
    List chat sessions for the authenticated tenant admin's organization.

    This endpoint is automatically scoped to the tenant from the JWT token.
    Tenant admins can only view sessions from their own organization.

    Args:
        limit: Maximum number of sessions to return (1-500)
        offset: Number of sessions to skip for pagination
        active_only: If True, only return active sessions
        claims: JWT token claims (automatically injected)
        db: Database session (automatically injected)

    Returns:
        List of chat sessions with metadata and message counts

    Raises:
        403: If user doesn't have ROLE_TENANT_ADMIN authority
    """
    logger.info(
        f"Tenant admin listing sessions - tenant_id: {claims.tenant_id}, "
        f"user_id: {claims.user_id}, limit: {limit}, offset: {offset}, "
        f"active_only: {active_only}"
    )

    # Build query - ALWAYS filtered by tenant_id from token
    query = db.query(ChatSession).filter(ChatSession.tenant_id == claims.tenant_id)

    # Apply active filter if requested
    if active_only:
        query = query.filter(ChatSession.is_active == True)

    # Order by last activity (most recent first)
    query = query.order_by(desc(ChatSession.last_activity))

    # Get total count for this tenant
    total = query.count()

    # Apply pagination
    sessions = query.offset(offset).limit(limit).all()

    # Get message counts for each session
    session_responses = []
    for session in sessions:
        message_count = db.query(ChatMessage).filter(
            ChatMessage.session_id == session.session_id
        ).count()

        session_responses.append(ChatSessionResponse(
            id=session.id,
            session_id=session.session_id,
            user_identifier=session.user_identifier,
            is_active=session.is_active,
            created_at=session.created_at,
            last_activity=session.last_activity,
            message_count=message_count
        ))

    logger.info(
        f"Returning {len(session_responses)} sessions for tenant {claims.tenant_id} "
        f"(total: {total})"
    )

    return session_responses


@router.get("/tenant/stats")
async def get_tenant_chat_stats(
    claims: TokenClaims = Depends(require_admin),  # TENANT_ADMIN only
    db: Session = Depends(get_db)
):
    """
    Get chat statistics for the authenticated tenant admin's organization.

    This endpoint is automatically scoped to the tenant from the JWT token.
    Returns aggregated statistics for the tenant's chat sessions and messages.

    Args:
        claims: JWT token claims (automatically injected)
        db: Database session (automatically injected)

    Returns:
        Chat statistics including session counts, message counts, and recent activity

    Raises:
        403: If user doesn't have ROLE_TENANT_ADMIN authority
    """
    logger.info(
        f"Tenant admin requesting stats - tenant_id: {claims.tenant_id}, "
        f"user_id: {claims.user_id}"
    )

    # All queries automatically filtered by tenant_id from token
    tenant_id = claims.tenant_id

    # Get session statistics
    total_sessions = db.query(ChatSession).filter(
        ChatSession.tenant_id == tenant_id
    ).count()

    active_sessions = db.query(ChatSession).filter(
        ChatSession.tenant_id == tenant_id,
        ChatSession.is_active == True
    ).count()

    # Get message statistics
    total_messages = db.query(ChatMessage).filter(
        ChatMessage.tenant_id == tenant_id
    ).count()

    user_messages = db.query(ChatMessage).filter(
        ChatMessage.tenant_id == tenant_id,
        ChatMessage.message_type == "user"
    ).count()

    assistant_messages = db.query(ChatMessage).filter(
        ChatMessage.tenant_id == tenant_id,
        ChatMessage.message_type == "assistant"
    ).count()

    # Get recent activity (last 24 hours)
    from datetime import timedelta
    yesterday = datetime.utcnow() - timedelta(days=1)
    recent_messages = db.query(ChatMessage).filter(
        ChatMessage.tenant_id == tenant_id,
        ChatMessage.created_at >= yesterday
    ).count()

    stats = {
        "total_sessions": total_sessions,
        "active_sessions": active_sessions,
        "total_messages": total_messages,
        "user_messages": user_messages,
        "assistant_messages": assistant_messages,
        "recent_messages_24h": recent_messages,
        "tenant_id": tenant_id
    }

    logger.info(
        f"Returning stats for tenant {tenant_id}: "
        f"sessions={total_sessions}, messages={total_messages}"
    )

    return stats


@router.get("/tenant/sessions/{session_id}", response_model=ChatSessionWithMessagesResponse)
async def get_tenant_chat_session(
    session_id: str,
    message_limit: int = Query(100, ge=1, le=1000, description="Max messages to return"),
    claims: TokenClaims = Depends(require_admin),  # TENANT_ADMIN only
    db: Session = Depends(get_db)
):
    """
    Get a specific chat session with its messages for tenant admin.

    This endpoint verifies the session belongs to the authenticated tenant
    before returning data. Tenant admins can only access their own sessions.

    Args:
        session_id: The session ID to retrieve
        message_limit: Maximum number of messages to return (1-1000)
        claims: JWT token claims (automatically injected)
        db: Database session (automatically injected)

    Returns:
        Complete session with messages

    Raises:
        403: If user doesn't have ROLE_TENANT_ADMIN authority
        404: If session not found or doesn't belong to tenant
    """
    logger.info(
        f"Tenant admin requesting session - session_id: {session_id}, "
        f"tenant_id: {claims.tenant_id}, user_id: {claims.user_id}"
    )

    # Get session and verify it belongs to this tenant
    session = db.query(ChatSession).filter(
        ChatSession.session_id == session_id,
        ChatSession.tenant_id == claims.tenant_id  # Security check
    ).first()

    if not session:
        logger.warning(
            f"Session not found or access denied - session_id: {session_id}, "
            f"tenant_id: {claims.tenant_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found or access denied"
        )

    # Get messages for this session
    messages = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).order_by(ChatMessage.created_at).limit(message_limit).all()

    # Get message count
    message_count = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).count()

    # Build response
    session_response = ChatSessionResponse(
        id=session.id,
        session_id=session.session_id,
        user_identifier=session.user_identifier,
        is_active=session.is_active,
        created_at=session.created_at,
        last_activity=session.last_activity,
        message_count=message_count
    )

    message_responses = [ChatMessageResponse.from_orm(message) for message in messages]

    logger.info(
        f"Returning session {session_id} with {len(message_responses)} messages "
        f"for tenant {claims.tenant_id}"
    )

    return ChatSessionWithMessagesResponse(
        session=session_response,
        messages=message_responses
    )


@router.get("/tenant/sessions/{session_id}/messages", response_model=List[ChatMessageResponse])
async def get_tenant_session_messages(
    session_id: str,
    limit: int = Query(100, ge=1, le=1000, description="Number of messages to return"),
    offset: int = Query(0, ge=0, description="Number of messages to skip"),
    claims: TokenClaims = Depends(require_admin),  # TENANT_ADMIN only
    db: Session = Depends(get_db)
):
    """
    Get messages for a specific chat session (tenant-scoped).

    This endpoint verifies the session belongs to the authenticated tenant
    before returning messages. Useful for pagination of messages.

    Args:
        session_id: The session ID to retrieve messages for
        limit: Maximum number of messages to return (1-1000)
        offset: Number of messages to skip for pagination
        claims: JWT token claims (automatically injected)
        db: Database session (automatically injected)

    Returns:
        List of chat messages ordered by creation time

    Raises:
        403: If user doesn't have ROLE_TENANT_ADMIN authority
        404: If session not found or doesn't belong to tenant
    """
    logger.info(
        f"Tenant admin requesting messages - session_id: {session_id}, "
        f"tenant_id: {claims.tenant_id}, user_id: {claims.user_id}, "
        f"limit: {limit}, offset: {offset}"
    )

    # Verify session belongs to this tenant
    session = db.query(ChatSession).filter(
        ChatSession.session_id == session_id,
        ChatSession.tenant_id == claims.tenant_id  # Security check
    ).first()

    if not session:
        logger.warning(
            f"Session not found or access denied - session_id: {session_id}, "
            f"tenant_id: {claims.tenant_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found or access denied"
        )

    # Get messages for this session
    messages = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).order_by(ChatMessage.created_at).offset(offset).limit(limit).all()

    logger.info(
        f"Returning {len(messages)} messages for session {session_id} "
        f"(tenant: {claims.tenant_id})"
    )

    return [ChatMessageResponse.from_orm(message) for message in messages]