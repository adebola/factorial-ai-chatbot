from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


class BackendCreateRequest(BaseModel):
    """Request to create a backend configuration."""
    tenant_id: str
    backend_type: str = Field(..., pattern="^(prometheus|alertmanager|elasticsearch|jaeger|kubernetes|otel_collector|llm)$")
    url: Optional[str] = None
    auth_type: str = Field(default="none", pattern="^(none|basic|bearer|service_account)$")
    credentials: Optional[Dict[str, Any]] = None  # Will be encrypted before storage
    verify_ssl: bool = True
    timeout_seconds: float = 10.0


class BackendUpdateRequest(BaseModel):
    """Request to update a backend configuration."""
    url: Optional[str] = None
    auth_type: Optional[str] = Field(default=None, pattern="^(none|basic|bearer|service_account)$")
    credentials: Optional[Dict[str, Any]] = None
    verify_ssl: Optional[bool] = None
    timeout_seconds: Optional[float] = None
    is_active: Optional[bool] = None


class BackendResponse(BaseModel):
    """Response for a backend configuration (credentials excluded)."""
    id: str
    tenant_id: str
    backend_type: str
    url: Optional[str] = None
    auth_type: str
    verify_ssl: bool
    timeout_seconds: float
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BackendTestResult(BaseModel):
    """Result of testing backend connectivity."""
    backend_type: str
    url: Optional[str] = None
    reachable: bool
    response_time_ms: Optional[float] = None
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
