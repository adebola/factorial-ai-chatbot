from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# --- Super-admin: LLM Provider catalog ---

class LLMProviderCreateRequest(BaseModel):
    """Request to add an LLM provider to the system catalog."""
    provider: str = Field(..., pattern="^(openai|anthropic|ollama|azure)$",
                          description="LLM provider type")
    model_id: str = Field(..., min_length=1, max_length=100,
                          description="Model identifier, e.g. 'gpt-4o', 'qwen3.5:9b'")
    display_name: str = Field(..., min_length=1, max_length=200,
                              description="Human-readable name, e.g. 'Local Qwen 3.5 9B'")
    base_url: Optional[str] = Field(None, description="Base URL (required for ollama/azure)")
    api_key: Optional[str] = Field(None, description="System-level API key (will be encrypted)")
    requires_api_key: bool = Field(True, description="False for local models like ollama")


class LLMProviderUpdateRequest(BaseModel):
    """Request to update an LLM provider in the catalog."""
    display_name: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    requires_api_key: Optional[bool] = None
    is_active: Optional[bool] = None


class LLMProviderResponse(BaseModel):
    """Response for an LLM provider (API key excluded)."""
    id: str
    provider: str
    model_id: str
    display_name: str
    base_url: Optional[str] = None
    requires_api_key: bool
    has_system_api_key: bool = False  # Computed: whether a system-level key is set
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# --- Tenant admin: LLM selection ---

class TenantLLMSelectRequest(BaseModel):
    """Request for a tenant admin to select an LLM provider."""
    llm_provider_id: str = Field(..., description="ID of the LLM provider from the catalog")
    api_key: Optional[str] = Field(None, description="Tenant-specific API key override (will be encrypted)")
    temperature: float = Field(0, ge=0, le=2, description="LLM temperature (0-2)")


class TenantLLMUpdateRequest(BaseModel):
    """Request to update tenant's LLM selection."""
    llm_provider_id: Optional[str] = None
    api_key: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0, le=2)


class TenantLLMSelectionResponse(BaseModel):
    """Response showing the tenant's current LLM selection."""
    id: str
    tenant_id: str
    llm_provider_id: str
    provider: str  # From joined LLMProvider
    model_id: str  # From joined LLMProvider
    display_name: str  # From joined LLMProvider
    base_url: Optional[str] = None  # From joined LLMProvider
    has_tenant_api_key: bool = False  # Whether tenant provided their own key
    temperature: float
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None