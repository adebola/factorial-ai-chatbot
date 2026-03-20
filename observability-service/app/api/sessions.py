"""
Observation session history API.
"""
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from ..core.database import get_db
from ..models.observation_session import ObservationSession
from ..models.observation_query import ObservationQuery
from ..schemas.session import SessionResponse, SessionDetailResponse, SessionListResponse
from ..schemas.observe import QueryHistoryItem
from ..services.dependencies import TokenClaims, validate_token

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    tenant_id: str = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """List observation sessions for a tenant."""
    target_tenant = tenant_id or claims.tenant_id

    if not claims.is_system_admin and target_tenant != claims.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot view sessions for other tenants"
        )

    query = db.query(ObservationSession).filter(
        ObservationSession.tenant_id == target_tenant
    ).order_by(desc(ObservationSession.created_at))

    total = query.count()
    sessions = query.offset(skip).limit(limit).all()

    return SessionListResponse(
        sessions=[SessionResponse.model_validate(s) for s in sessions],
        total=total
    )


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: str,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """Get session details with query history."""
    session = db.query(ObservationSession).filter(
        ObservationSession.id == session_id
    ).first()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )

    if not claims.is_system_admin and session.tenant_id != claims.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot view sessions for other tenants"
        )

    queries = db.query(ObservationQuery).filter(
        ObservationQuery.session_id == session_id
    ).order_by(ObservationQuery.created_at).all()

    return SessionDetailResponse(
        id=session.id,
        tenant_id=session.tenant_id,
        chat_session_id=session.chat_session_id,
        created_at=session.created_at,
        updated_at=session.updated_at,
        queries=[QueryHistoryItem.model_validate(q) for q in queries]
    )


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """Delete a session and its queries."""
    session = db.query(ObservationSession).filter(
        ObservationSession.id == session_id
    ).first()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )

    if not claims.is_system_admin and session.tenant_id != claims.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete sessions for other tenants"
        )

    # Delete queries first
    db.query(ObservationQuery).filter(
        ObservationQuery.session_id == session_id
    ).delete()

    db.delete(session)
    db.commit()
