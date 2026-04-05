from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class AuditEventResponse(BaseModel):
    id: str
    event_id: str
    tenant_id: str
    actor_user_id: Optional[str] = None
    actor_email: Optional[str] = None
    actor_type: str
    action_type: str
    tier: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    source_service: str
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    before_state: Optional[Dict[str, Any]] = None
    after_state: Optional[Dict[str, Any]] = None
    event_metadata: Optional[Dict[str, Any]] = None
    occurred_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class AuditEventListResponse(BaseModel):
    items: List[AuditEventResponse]
    total: int
    page: int
    size: int


class AuditStatsResponse(BaseModel):
    total_events: int
    by_tier: Dict[str, int]
    by_service: Dict[str, int]
    by_action_type: Dict[str, int]
