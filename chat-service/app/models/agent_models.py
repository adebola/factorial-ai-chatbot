"""Models for Agent Chat Sessions and Messages.

These are separate from RAG chat models (ChatSession/ChatMessage) because
agent conversations have different requirements:
- OAuth2 authenticated users (not anonymous)
- Token-counted messages for context window management
- Structured content blocks for rich rendering
- Session chaining for context overflow carry-over
"""
import uuid
from sqlalchemy import (
    Column, String, Text, Boolean, DateTime, JSON, Integer,
    ForeignKey, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .chat_models import Base


def generate_uuid():
    return str(uuid.uuid4())


class AgentSession(Base):
    """A conversation session between a tenant user and an agentic service."""
    __tablename__ = "agent_sessions"
    __table_args__ = (
        Index("idx_agent_sessions_tenant_service_status", "tenant_id", "service_key", "status"),
        Index("idx_agent_sessions_user", "user_id"),
    )

    id = Column(String(36), primary_key=True, index=True, default=generate_uuid)
    tenant_id = Column(String(36), nullable=False, index=True)
    user_id = Column(String(36), nullable=False)
    user_email = Column(String(255), nullable=True)
    user_full_name = Column(String(255), nullable=True)
    service_key = Column(String(50), nullable=False, index=True)
    parent_session_id = Column(String(36), nullable=True)
    context_summary = Column(Text, nullable=True)
    model_name = Column(String(100), nullable=True)
    total_tokens_used = Column(Integer, nullable=False, default=0)
    context_limit_tokens = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False, default="active")  # active | completed | context_overflow
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_activity = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    messages = relationship("AgentMessage", back_populates="session", order_by="AgentMessage.created_at")


class AgentMessage(Base):
    """A single message in an agent conversation session."""
    __tablename__ = "agent_messages"

    id = Column(String(36), primary_key=True, index=True, default=generate_uuid)
    session_id = Column(String(36), ForeignKey("agent_sessions.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # user | assistant | system | tool
    content = Column(Text, nullable=True)
    structured_blocks = Column(JSON, nullable=True)
    token_count = Column(Integer, nullable=False, default=0)
    tool_calls = Column(JSON, nullable=True)
    message_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("AgentSession", back_populates="messages")
