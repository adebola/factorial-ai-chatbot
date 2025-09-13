from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field

from ..core.database import get_db
from ..models.chat_models import ChatSession, ChatMessage
from ..core.logging_config import get_logger
from ..services.dependencies import validate_token, TokenClaims

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
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """List all chat sessions for the authenticated tenant"""
    tenant_id = claims.tenant_id
    
    logger.info("Listing chat sessions", tenant_id=tenant_id, limit=limit, offset=offset)
    
    # Build query
    query = db.query(ChatSession).filter(ChatSession.tenant_id == tenant_id)
    
    if active_only:
        query = query.filter(ChatSession.is_active == True)
    
    # Get sessions with message count
    sessions = query.order_by(desc(ChatSession.last_activity)).offset(offset).limit(limit).all()
    
    # Add a message count to each session
    session_responses = []
    for session in sessions:
        message_count = db.query(ChatMessage).filter(
            and_(
                ChatMessage.tenant_id == tenant_id,
                ChatMessage.session_id == session.session_id
            )
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
    
    logger.info("Retrieved chat sessions", tenant_id=tenant_id, count=len(session_responses))
    return session_responses


@router.get("/admin/sessions/{session_id}/messages", response_model=List[ChatMessageResponse])
async def get_session_messages(
    session_id: str,
    limit: int = Query(100, ge=1, le=1000, description="Number of messages to return"),
    offset: int = Query(0, ge=0, description="Number of messages to skip"),
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """Get all messages for a specific chat session"""
    tenant_id = claims.tenant_id
    
    logger.info("Getting session messages", tenant_id=tenant_id, session_id=session_id)
    
    # Verify session belongs to tenant
    session = db.query(ChatSession).filter(
        and_(
            ChatSession.session_id == session_id,
            ChatSession.tenant_id == tenant_id
        )
    ).first()
    
    if not session:
        logger.warning("Session not found", tenant_id=tenant_id, session_id=session_id)
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get messages for the session
    messages = db.query(ChatMessage).filter(
        and_(
            ChatMessage.tenant_id == tenant_id,
            ChatMessage.session_id == session_id
        )
    ).order_by(ChatMessage.created_at).offset(offset).limit(limit).all()
    
    logger.info("Retrieved session messages", 
               tenant_id=tenant_id, 
               session_id=session_id, 
               count=len(messages))
    
    return [ChatMessageResponse.from_orm(message) for message in messages]


@router.get("/admin/sessions/{session_id}", response_model=ChatSessionWithMessagesResponse)
async def get_session_with_messages(
    session_id: str,
    message_limit: int = Query(100, ge=1, le=1000, description="Number of messages to return"),
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """Get a complete chat session with all messages"""
    tenant_id = claims.tenant_id
    
    logger.info("Getting complete session", tenant_id=tenant_id, session_id=session_id)
    
    # Get session
    session = db.query(ChatSession).filter(
        and_(
            ChatSession.session_id == session_id,
            ChatSession.tenant_id == tenant_id
        )
    ).first()
    
    if not session:
        logger.warning("Session not found", tenant_id=tenant_id, session_id=session_id)
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get messages for the session
    messages = db.query(ChatMessage).filter(
        and_(
            ChatMessage.tenant_id == tenant_id,
            ChatMessage.session_id == session_id
        )
    ).order_by(ChatMessage.created_at).limit(message_limit).all()
    
    # Get message count
    message_count = db.query(ChatMessage).filter(
        and_(
            ChatMessage.tenant_id == tenant_id,
            ChatMessage.session_id == session_id
        )
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
    
    logger.info("Retrieved complete session", 
               tenant_id=tenant_id, 
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
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """Search messages by content"""
    tenant_id = claims.tenant_id
    
    logger.info("Searching messages", 
               tenant_id=tenant_id, 
               query=query, 
               message_type=message_type,
               session_id=session_id)
    
    # Build search query
    search_query = db.query(ChatMessage).filter(
        and_(
            ChatMessage.tenant_id == tenant_id,
            ChatMessage.content.ilike(f"%{query}%")
        )
    )
    
    # Apply filters
    if message_type:
        search_query = search_query.filter(ChatMessage.message_type == message_type)
    
    if session_id:
        search_query = search_query.filter(ChatMessage.session_id == session_id)
    
    # Execute query
    messages = search_query.order_by(desc(ChatMessage.created_at)).offset(offset).limit(limit).all()
    
    logger.info("Message search results", 
               tenant_id=tenant_id, 
               query=query, 
               count=len(messages))
    
    return [ChatMessageResponse.from_orm(message) for message in messages]


@router.get("/admin/stats")
async def get_chat_stats(
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """Get chat statistics for the tenant"""
    tenant_id = claims.tenant_id
    
    logger.info("Getting chat stats", tenant_id=tenant_id)
    
    # Get various stats
    total_sessions = db.query(ChatSession).filter(ChatSession.tenant_id == tenant_id).count()
    active_sessions = db.query(ChatSession).filter(
        and_(
            ChatSession.tenant_id == tenant_id,
            ChatSession.is_active == True
        )
    ).count()
    
    total_messages = db.query(ChatMessage).filter(ChatMessage.tenant_id == tenant_id).count()
    user_messages = db.query(ChatMessage).filter(
        and_(
            ChatMessage.tenant_id == tenant_id,
            ChatMessage.message_type == "user"
        )
    ).count()
    assistant_messages = db.query(ChatMessage).filter(
        and_(
            ChatMessage.tenant_id == tenant_id,
            ChatMessage.message_type == "assistant"
        )
    ).count()
    
    # Get recent activity (last 24 hours)
    from datetime import timedelta
    yesterday = datetime.utcnow() - timedelta(days=1)
    recent_messages = db.query(ChatMessage).filter(
        and_(
            ChatMessage.tenant_id == tenant_id,
            ChatMessage.created_at >= yesterday
        )
    ).count()
    
    stats = {
        "total_sessions": total_sessions,
        "active_sessions": active_sessions,
        "total_messages": total_messages,
        "user_messages": user_messages,
        "assistant_messages": assistant_messages,
        "recent_messages_24h": recent_messages
    }
    
    logger.info("Retrieved chat stats", tenant_id=tenant_id, stats=stats)
    return stats