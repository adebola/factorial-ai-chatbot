"""Internal REST endpoint used by other backend services (e.g.
communications-service for WhatsApp) to generate an AI reply via the existing
RAG pipeline without going through the WebSocket flow.

This is NOT a public-facing endpoint. It is gated by a static
X-Internal-Service-Token header validated against an env var, and it should
NOT be exposed through the public gateway allow-list.
"""
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.logging_config import get_logger
from ..models.chat_models import ChatMessage, ChatSession
from ..services.chat_service import ChatService
from ..services.dependencies import validate_internal_service


router = APIRouter()
logger = get_logger("internal_chat_api")


class GenerateRequest(BaseModel):
    tenant_id: str = Field(..., min_length=1)
    user_identifier: str = Field(..., min_length=1, description="Stable per-end-user ID for the channel (e.g. WhatsApp E.164)")
    message: str = Field(..., min_length=1)
    session_id: Optional[str] = Field(default=None, description="If provided, append to that session; otherwise resolve-or-create one for the user_identifier")
    channel: Optional[str] = Field(default=None, description="Originating channel, stored in message_metadata (e.g. 'whatsapp')")


class GenerateResponse(BaseModel):
    content: str
    sources: List[Any] = []
    session_id: str
    metadata: Dict[str, Any] = {}


def _resolve_or_create_session(
    db: Session,
    tenant_id: str,
    user_identifier: str,
    requested_session_id: Optional[str],
) -> ChatSession:
    """Return an active ChatSession for this (tenant_id, user_identifier).

    If `requested_session_id` is supplied and matches an existing session for
    the same tenant, prefer it. Otherwise, return the most-recent active
    session, or create a new one.
    """
    if requested_session_id:
        existing = (
            db.query(ChatSession)
            .filter(
                ChatSession.tenant_id == tenant_id,
                ChatSession.session_id == requested_session_id,
            )
            .first()
        )
        if existing:
            return existing

    active = (
        db.query(ChatSession)
        .filter(
            ChatSession.tenant_id == tenant_id,
            ChatSession.user_identifier == user_identifier,
            ChatSession.is_active == True,  # noqa: E712 — SQLAlchemy column comparison
        )
        .order_by(ChatSession.created_at.desc())
        .first()
    )
    if active:
        return active

    session = ChatSession(
        tenant_id=tenant_id,
        session_id=str(uuid.uuid4()),
        user_identifier=user_identifier,
        is_active=True,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.post(
    "/internal/chat/generate",
    response_model=GenerateResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(validate_internal_service)],
)
async def generate(
    request: GenerateRequest,
    db: Session = Depends(get_db),
) -> GenerateResponse:
    """Generate an AI reply for a backend-initiated message.

    Persists both the user message and the AI reply as ChatMessage rows so the
    conversation shows up in the same admin views as widget chats.
    """
    session = _resolve_or_create_session(
        db=db,
        tenant_id=request.tenant_id,
        user_identifier=request.user_identifier,
        requested_session_id=request.session_id,
    )

    channel = request.channel or "internal"
    base_metadata = {"user_identifier": request.user_identifier, "channel": channel}

    # Persist the user message before AI generation
    user_msg = ChatMessage(
        tenant_id=request.tenant_id,
        session_id=session.session_id,
        message_type="user",
        content=request.message,
        message_metadata=base_metadata,
    )
    db.add(user_msg)
    db.commit()

    chat_service = ChatService(db)
    try:
        reply = await chat_service.generate_response(
            tenant_id=request.tenant_id,
            user_message=request.message,
            session_id=session.session_id,
        )
    except ValueError as exc:
        # ChatService raises ValueError("Tenant not found")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Internal chat generate failed",
            tenant_id=request.tenant_id,
            session_id=session.session_id,
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to generate response: {exc}",
        )

    # Persist the assistant message with sources + token usage in metadata
    assistant_metadata = {
        **base_metadata,
        "sources": reply.get("sources", []),
        "token_usage": reply.get("token_usage"),
    }
    assistant_msg = ChatMessage(
        tenant_id=request.tenant_id,
        session_id=session.session_id,
        message_type="assistant",
        content=reply.get("content", ""),
        message_metadata=assistant_metadata,
    )
    db.add(assistant_msg)
    db.commit()

    return GenerateResponse(
        content=reply.get("content", ""),
        sources=reply.get("sources", []),
        session_id=session.session_id,
        metadata=reply.get("metadata", {}),
    )
