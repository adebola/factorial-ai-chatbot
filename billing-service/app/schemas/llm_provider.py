"""Pydantic schemas for the LLM Provider Config registry."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class LLMProviderConfigCreate(BaseModel):
    provider: str = Field(..., min_length=1, max_length=50)
    model_name: str = Field(..., min_length=1, max_length=100)
    display_name: Optional[str] = Field(None, max_length=200)
    max_context_tokens: int = Field(..., gt=0)
    context_limit_tokens: int = Field(..., gt=0)
    max_response_tokens: int = Field(default=4096, gt=0)
    cost_per_input_token: float = Field(default=0.0, ge=0)
    cost_per_output_token: float = Field(default=0.0, ge=0)


class LLMProviderConfigUpdate(BaseModel):
    display_name: Optional[str] = Field(None, max_length=200)
    max_context_tokens: Optional[int] = Field(None, gt=0)
    context_limit_tokens: Optional[int] = Field(None, gt=0)
    max_response_tokens: Optional[int] = Field(None, gt=0)
    cost_per_input_token: Optional[float] = Field(None, ge=0)
    cost_per_output_token: Optional[float] = Field(None, ge=0)
    is_active: Optional[bool] = None


class LLMProviderConfigResponse(BaseModel):
    id: str
    provider: str
    model_name: str
    display_name: Optional[str] = None
    max_context_tokens: int
    context_limit_tokens: int
    max_response_tokens: int
    cost_per_input_token: float
    cost_per_output_token: float
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
