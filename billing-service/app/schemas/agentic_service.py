"""Pydantic schemas for the Agentic Service Registry."""
from datetime import datetime
from typing import Optional, Dict, Any, List

from pydantic import BaseModel, Field


# ── Service Catalog ──

class ServiceCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    service_key: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-z0-9_-]+$")
    description: Optional[str] = None
    base_url: Optional[str] = None
    health_check_url: Optional[str] = None
    category: str = Field(default="agentic", max_length=50)
    icon_url: Optional[str] = None
    capabilities: Optional[Dict[str, Any]] = None
    ui_hints: Optional[Dict[str, Any]] = None


class ServiceUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    base_url: Optional[str] = None
    health_check_url: Optional[str] = None
    category: Optional[str] = Field(None, max_length=50)
    is_active: Optional[bool] = None
    icon_url: Optional[str] = None
    capabilities: Optional[Dict[str, Any]] = None
    ui_hints: Optional[Dict[str, Any]] = None


class ServiceResponse(BaseModel):
    id: str
    name: str
    service_key: str
    description: Optional[str] = None
    base_url: Optional[str] = None
    health_check_url: Optional[str] = None
    category: str
    icon_url: Optional[str] = None
    capabilities: Optional[Dict[str, Any]] = None
    ui_hints: Optional[Dict[str, Any]] = None
    is_active: bool
    tenant_count: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── Tenant Assignment ──

class AssignRequest(BaseModel):
    tenant_id: str = Field(..., min_length=1, max_length=36)
    config: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None


class AssignmentUpdateRequest(BaseModel):
    config: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class AssignmentResponse(BaseModel):
    id: str
    tenant_id: str
    service_id: str
    assigned_by: str
    assigned_by_email: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None
    is_active: bool
    deactivated_at: Optional[datetime] = None
    deactivated_by: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── Service Access Check ──

class ServiceAccessResponse(BaseModel):
    allowed: bool
    service_key: str
    config: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None


# ── Active Agentic Service Check ──

class ActiveAgenticServiceResponse(BaseModel):
    """Response for checking a tenant's active agentic service."""
    has_service: bool
    service_key: Optional[str] = None
    service_name: Optional[str] = None
    base_url: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


# ── Tenant-Facing ──

class TenantServiceResponse(BaseModel):
    id: str
    name: str
    service_key: str
    description: Optional[str] = None
    category: str
    config: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


# ── Multi-Agent Tenant Lookup ──

class ActiveAgenticServiceDetail(BaseModel):
    """Detail for a single active agentic service assigned to a tenant."""
    service_key: str
    service_name: str
    base_url: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    icon_url: Optional[str] = None
    capabilities: Optional[Dict[str, Any]] = None
    ui_hints: Optional[Dict[str, Any]] = None
    config: Optional[Dict[str, Any]] = None


class ActiveAgenticServicesResponse(BaseModel):
    """Response for checking all active agentic services for a tenant."""
    has_services: bool
    services: List[ActiveAgenticServiceDetail] = []
