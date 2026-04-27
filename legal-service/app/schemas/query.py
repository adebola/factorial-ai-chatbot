from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    tenant_id: str
    session_id: Optional[str] = None
    message: str = Field(..., min_length=1)
    conversation_history: List[Dict[str, str]] = Field(default_factory=list)
    workspace_id: Optional[str] = None


class ToolCallDetail(BaseModel):
    tool: str
    input: Dict[str, Any] = Field(default_factory=dict)
    output: str = ""


class QueryResponse(BaseModel):
    response: str
    tool_calls: List[ToolCallDetail] = Field(default_factory=list)
    query_id: Optional[str] = None
    total_duration_ms: Optional[float] = None
    suggested_actions: List[str] = Field(default_factory=list)
