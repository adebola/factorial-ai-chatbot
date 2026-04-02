from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class ObserveRequest(BaseModel):
    """Request to query the observability agent."""
    tenant_id: str
    session_id: Optional[str] = None
    message: str = Field(..., min_length=1, max_length=5000)
    conversation_history: Optional[List[Dict[str, str]]] = None


class ToolCallDetail(BaseModel):
    """Detail of a single tool call made by the agent."""
    tool: str
    input: Dict[str, Any]
    output: str
    duration_ms: float


class ContentBlock(BaseModel):
    """A single renderable content block in a rich agent response."""
    type: str                                      # text, table, chart, diagram, code, image, alert
    content: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    language: Optional[str] = None
    format: Optional[str] = None
    chart_type: Optional[str] = None
    url: Optional[str] = None
    alt: Optional[str] = None
    severity: Optional[str] = None


class ObserveResponse(BaseModel):
    """Response from the observability agent."""
    response: str
    response_type: str = "rich"
    blocks: List[ContentBlock] = []
    tool_calls: List[ToolCallDetail] = []
    suggested_actions: List[str] = []
    session_id: str
    query_id: str
    total_duration_ms: float
    llm_tokens_used: Optional[int] = None


class ObserveErrorResponse(BaseModel):
    """Error response from the observability agent."""
    error: str
    session_id: Optional[str] = None
    query_id: Optional[str] = None


class QueryHistoryItem(BaseModel):
    """A single query in session history."""
    id: str
    user_message: str
    agent_response: Optional[str] = None
    tool_calls: Optional[List[ToolCallDetail]] = None
    total_duration_ms: Optional[float] = None
    llm_tokens_used: Optional[int] = None
    status: str
    error_message: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
