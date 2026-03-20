from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from .observe import QueryHistoryItem


class SessionResponse(BaseModel):
    """Response for a single observation session."""
    id: str
    tenant_id: str
    chat_session_id: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SessionDetailResponse(SessionResponse):
    """Session with query history."""
    queries: List[QueryHistoryItem] = []


class SessionListResponse(BaseModel):
    """Paginated session list."""
    sessions: List[SessionResponse]
    total: int
