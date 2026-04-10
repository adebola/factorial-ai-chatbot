"""Pydantic schemas for the Agentic Service Registry."""
from datetime import datetime
from typing import Optional, Dict, Any, List, Literal

from pydantic import BaseModel, Field, field_validator


def _empty_str_to_none(v: Any) -> Any:
    """Coerce empty / whitespace-only strings to None.

    Useful for Optional[Dict[...]] fields that the admin form may submit as ""
    when the user clears the textarea. Without this, Pydantic v2 raises a
    `dict_type` validation error and the request fails with 422.
    """
    if isinstance(v, str) and v.strip() == "":
        return None
    return v


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

    _empty_capabilities = field_validator("capabilities", mode="before")(_empty_str_to_none)
    _empty_ui_hints = field_validator("ui_hints", mode="before")(_empty_str_to_none)


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

    _empty_capabilities = field_validator("capabilities", mode="before")(_empty_str_to_none)
    _empty_ui_hints = field_validator("ui_hints", mode="before")(_empty_str_to_none)


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
    ui_extensions: Optional[List[Dict[str, Any]]] = None
    health_status: str = "unknown"
    last_manifest_fetch_at: Optional[datetime] = None
    last_health_at: Optional[datetime] = None
    is_active: bool
    tenant_count: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── Plugin Manifest ──
#
# The contract every agentic/plugin service must implement at GET /manifest.
# Manifests are intentionally opaque to the core — the catalog stores them as
# JSON and replays them to consumers (the superadmin shell, primarily).

class PluginUiExtension(BaseModel):
    """One admin-UI menu entry contributed by a plugin."""
    menu_label: str = Field(..., min_length=1, max_length=100)
    icon: Optional[str] = Field(None, max_length=50)
    route: str = Field(..., min_length=1, max_length=100)
    required_role: Literal["SUPER_ADMIN", "TENANT_ADMIN", "ANY"] = "SUPER_ADMIN"
    api_prefix: Optional[str] = Field(
        None,
        description="Path prefix that the gateway exposes for this extension's "
                    "backend calls. Used by the frontend to construct API URLs.",
        max_length=200,
    )


class PluginManifest(BaseModel):
    """Self-description returned by a plugin's GET /manifest endpoint."""
    service_key: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(..., min_length=1, max_length=100)
    version: str = Field(..., min_length=1, max_length=20)
    category: str = Field(default="agentic", max_length=50)
    description: Optional[str] = None
    capabilities: Optional[Dict[str, Any]] = None
    triggers: Optional[List[str]] = None
    ui_extensions: List[PluginUiExtension] = Field(default_factory=list)
    settings_schema: Optional[Dict[str, Any]] = None


class RegisterByUrlRequest(BaseModel):
    base_url: str = Field(..., min_length=1, max_length=500)
    health_check_url: Optional[str] = Field(None, max_length=500)
    manifest_path: str = Field(default="/manifest", max_length=100)


class UiExtensionEntry(BaseModel):
    """Flattened UI extension entry returned to the superadmin shell."""
    service_id: str
    service_key: str
    service_name: str
    menu_label: str
    icon: Optional[str] = None
    route: str
    required_role: str
    api_prefix: Optional[str] = None
    health_status: str


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
