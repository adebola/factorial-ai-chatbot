from sqlalchemy import Column, String, DateTime, Boolean, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
import uuid

Base = declarative_base()


def generate_uuid():
    """Generate UUID string for primary keys"""
    return str(uuid.uuid4())


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    
    id = Column(String(36), primary_key=True, index=True, default=generate_uuid)
    tenant_id = Column(String(255), nullable=False, index=True)
    session_id = Column(String(255), unique=True, index=True)
    user_identifier = Column(String(255))  # For tracking user within tenant
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_activity = Column(DateTime(timezone=True), onupdate=func.now())


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    
    id = Column(String(36), primary_key=True, index=True, default=generate_uuid)
    tenant_id = Column(String(255), nullable=False, index=True)
    session_id = Column(String(255), nullable=False, index=True)
    message_type = Column(String(20), nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    message_metadata = Column(JSON, default={})  # Store additional context, sources, etc.
    created_at = Column(DateTime(timezone=True), server_default=func.now())