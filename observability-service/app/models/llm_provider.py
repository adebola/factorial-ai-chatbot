import uuid
from sqlalchemy import Column, String, Boolean, Float, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..core.database import Base


class LLMProvider(Base):
    """System-wide catalog of available LLM providers (managed by super-admin)."""
    __tablename__ = "llm_providers"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    provider = Column(String(50), nullable=False)  # openai, anthropic, ollama, azure
    model_id = Column(String(100), nullable=False)  # gpt-4o, claude-sonnet-4-6, qwen3.5:9b
    display_name = Column(String(200), nullable=False)  # Human-readable name
    base_url = Column(String(500), nullable=True)  # Required for ollama/azure, optional for openai/anthropic
    api_key_encrypted = Column(Text, nullable=True)  # System-level API key (encrypted)
    requires_api_key = Column(Boolean, default=True, nullable=False)  # False for local models like ollama
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    tenant_selections = relationship("TenantLLMSelection", back_populates="llm_provider")

    __table_args__ = (
        UniqueConstraint("provider", "model_id", name="uq_provider_model"),
    )


class TenantLLMSelection(Base):
    """Per-tenant LLM selection from the provider catalog."""
    __tablename__ = "tenant_llm_selections"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), nullable=False, index=True)
    llm_provider_id = Column(String(36), ForeignKey("llm_providers.id"), nullable=False)
    api_key_encrypted = Column(Text, nullable=True)  # Tenant-level override (encrypted)
    temperature = Column(Float, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    llm_provider = relationship("LLMProvider", back_populates="tenant_selections")

    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_tenant_llm_selection"),
    )