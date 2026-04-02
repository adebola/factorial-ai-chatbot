"""Service layer for agent chat session management.

Handles session CRUD, message persistence with token counting,
Redis dual-write for fast context retrieval, and session overflow.
"""
import json
import os
from typing import List, Optional, Tuple

import redis.asyncio as aioredis
from sqlalchemy.orm import Session

from ..core.logging_config import get_logger
from ..models.agent_models import AgentSession, AgentMessage

logger = get_logger("agent_session")

AGENT_CHAT_TTL = 72 * 3600  # 72 hours


class AgentSessionService:
    """Manages agent conversation sessions and messages."""

    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
            self._redis = aioredis.from_url(redis_url, decode_responses=True)
        return self._redis

    # ── Session Management ──

    def get_or_create_session(
        self,
        db: Session,
        tenant_id: str,
        user_id: str,
        user_email: str,
        user_full_name: str,
        service_key: str,
        session_id: Optional[str] = None,
        model_name: Optional[str] = None,
        context_limit_tokens: Optional[int] = None,
    ) -> Tuple[AgentSession, bool]:
        """
        Get an existing active session or create a new one.
        Returns (session, is_new).
        """
        if session_id:
            existing = db.query(AgentSession).filter(
                AgentSession.id == session_id,
                AgentSession.tenant_id == tenant_id,
                AgentSession.user_id == user_id,
                AgentSession.service_key == service_key,
            ).first()
            if existing and existing.status == "active":
                return existing, False

        # No explicit session_id (or it wasn't found) — resume most recent active session
        latest_active = (
            db.query(AgentSession)
            .filter(
                AgentSession.tenant_id == tenant_id,
                AgentSession.user_id == user_id,
                AgentSession.service_key == service_key,
                AgentSession.status == "active",
            )
            .order_by(AgentSession.last_activity.desc())
            .first()
        )
        if latest_active:
            logger.info(
                "Resuming most recent active session",
                session_id=latest_active.id,
                tenant_id=tenant_id,
                service_key=service_key,
            )
            return latest_active, False

        # Create new session
        session = AgentSession(
            tenant_id=tenant_id,
            user_id=user_id,
            user_email=user_email,
            user_full_name=user_full_name,
            service_key=service_key,
            model_name=model_name,
            context_limit_tokens=context_limit_tokens,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        logger.info(
            "Created new agent session",
            session_id=session.id,
            tenant_id=tenant_id,
            service_key=service_key,
        )
        return session, True

    def get_session(self, db: Session, session_id: str) -> Optional[AgentSession]:
        return db.query(AgentSession).filter(AgentSession.id == session_id).first()

    def list_sessions(
        self, db: Session, tenant_id: str, user_id: str, service_key: str
    ) -> List[AgentSession]:
        """List all sessions for a user+service, ordered by most recent."""
        return (
            db.query(AgentSession)
            .filter(
                AgentSession.tenant_id == tenant_id,
                AgentSession.user_id == user_id,
                AgentSession.service_key == service_key,
            )
            .order_by(AgentSession.last_activity.desc())
            .all()
        )

    # ── Message Persistence ──

    async def save_message(
        self,
        db: Session,
        session: AgentSession,
        role: str,
        content: str,
        token_count: int,
        structured_blocks: Optional[dict] = None,
        tool_calls: Optional[list] = None,
        metadata: Optional[dict] = None,
    ) -> AgentMessage:
        """Save a message with pre-computed token count and dual-write to Redis."""
        message = AgentMessage(
            session_id=session.id,
            role=role,
            content=content,
            structured_blocks=structured_blocks,
            token_count=token_count,
            tool_calls=tool_calls,
            message_metadata=metadata,
        )
        db.add(message)

        # Update session running total
        session.total_tokens_used = (session.total_tokens_used or 0) + token_count
        db.commit()
        db.refresh(message)

        # Dual-write to Redis (fire-and-forget)
        try:
            await self._cache_message(session.id, message)
        except Exception as e:
            logger.warning("Failed to cache message to Redis", error=str(e))

        return message

    async def get_conversation_history(
        self, db: Session, session_id: str
    ) -> List[dict]:
        """Get message history from Redis cache, falling back to DB."""
        try:
            r = await self._get_redis()
            key = f"agent_chat:{session_id}"
            cached = await r.lrange(key, 0, -1)
            if cached:
                return [json.loads(m) for m in cached]
        except Exception as e:
            logger.warning("Redis cache miss or error, falling back to DB", error=str(e))

        # Rebuild from DB
        messages = (
            db.query(AgentMessage)
            .filter(AgentMessage.session_id == session_id)
            .order_by(AgentMessage.created_at)
            .all()
        )
        history = []
        for msg in messages:
            entry = {
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "token_count": msg.token_count,
                "structured_blocks": msg.structured_blocks,
                "tool_calls": msg.tool_calls,
                "message_metadata": msg.message_metadata,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
            }
            history.append(entry)
            # Re-populate Redis
            try:
                await self._cache_message_raw(session_id, entry)
            except Exception:
                pass

        return history

    # ── Session Overflow ──

    def check_overflow(
        self, session: AgentSession, new_message_tokens: int, max_response_tokens: int = 4096
    ) -> bool:
        """Check if adding a new message would exceed the session's context limit."""
        if not session.context_limit_tokens:
            return False  # No limit configured
        projected = (session.total_tokens_used or 0) + new_message_tokens + max_response_tokens
        return projected > session.context_limit_tokens

    def handle_overflow(
        self,
        db: Session,
        session: AgentSession,
        context_summary: Optional[str] = None,
    ) -> AgentSession:
        """
        Mark current session as overflowed and create a new continuation session.
        """
        session.status = "context_overflow"
        db.commit()

        new_session = AgentSession(
            tenant_id=session.tenant_id,
            user_id=session.user_id,
            user_email=session.user_email,
            user_full_name=session.user_full_name,
            service_key=session.service_key,
            parent_session_id=session.id,
            context_summary=context_summary,
            model_name=session.model_name,
            context_limit_tokens=session.context_limit_tokens,
            status="active",
        )
        db.add(new_session)
        db.commit()
        db.refresh(new_session)

        logger.info(
            "Session overflow handled",
            old_session_id=session.id,
            new_session_id=new_session.id,
            carry_over=context_summary is not None,
        )
        return new_session

    # ── Redis Helpers ──

    async def _cache_message(self, session_id: str, message: AgentMessage):
        entry = {
            "id": message.id,
            "role": message.role,
            "content": message.content,
            "token_count": message.token_count,
            "structured_blocks": message.structured_blocks,
            "tool_calls": message.tool_calls,
            "message_metadata": message.message_metadata,
            "created_at": message.created_at.isoformat() if message.created_at else None,
        }
        await self._cache_message_raw(session_id, entry)

    async def _cache_message_raw(self, session_id: str, entry: dict):
        r = await self._get_redis()
        key = f"agent_chat:{session_id}"
        await r.rpush(key, json.dumps(entry, default=str))
        await r.expire(key, AGENT_CHAT_TTL)

    async def close(self):
        if self._redis:
            await self._redis.close()
            self._redis = None


# Module-level singleton
agent_session_service = AgentSessionService()
