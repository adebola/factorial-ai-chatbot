"""Platform-wide LLM Provider configuration model.

Managed by super-admin to define available models and their context
window limits. Used by the agent gateway to enforce token budgets
and by the super-admin UI to configure model availability.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, UniqueConstraint

from ..core.database import Base


class LLMProviderConfig(Base):
    """Configuration for an LLM model available on the platform."""
    __tablename__ = "llm_provider_configs"
    __table_args__ = (
        UniqueConstraint("provider", "model_name", name="uq_provider_model"),
    )

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    provider = Column(String(50), nullable=False)        # openai | anthropic | ollama | azure
    model_name = Column(String(100), nullable=False)     # gpt-4o, claude-sonnet-4-20250514, etc.
    display_name = Column(String(200), nullable=True)
    max_context_tokens = Column(Integer, nullable=False)  # model's total context window
    context_limit_tokens = Column(Integer, nullable=False) # admin-configured usable limit
    max_response_tokens = Column(Integer, nullable=False, default=4096)
    cost_per_input_token = Column(Float, nullable=False, default=0.0)
    cost_per_output_token = Column(Float, nullable=False, default=0.0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=lambda: datetime.now(timezone.utc))
