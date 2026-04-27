"""
POST /query endpoint — executes a legal intelligence query through the
LangGraph ReAct agent.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status

from ..schemas.query import QueryRequest, QueryResponse, ToolCallDetail
from ..services.dependencies import TokenClaims, validate_token
from ..services.agent_service import execute_query

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/query", response_model=QueryResponse)
async def legal_query(
    request: QueryRequest,
    claims: TokenClaims = Depends(validate_token),
):
    """Run a legal intelligence query against the workspace documents."""

    # Override tenant_id from token — never trust the request body
    tenant_id = claims.tenant_id

    if not request.workspace_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="workspace_id is required",
        )

    result = await execute_query(
        tenant_id=tenant_id,
        workspace_id=request.workspace_id,
        message=request.message,
        conversation_history=request.conversation_history,
        access_token=claims.access_token,
    )

    # Handle agent-level errors
    if result.get("error"):
        logger.error(f"Agent error for tenant {tenant_id}: {result['error']}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Legal analysis failed: {result['error']}",
        )

    # Map tool calls to response schema
    tool_call_details = [
        ToolCallDetail(
            tool=tc["tool"],
            input=tc.get("input", {}),
            output=tc.get("output", ""),
        )
        for tc in result.get("tool_calls", [])
    ]

    return QueryResponse(
        response=result["response"],
        tool_calls=tool_call_details,
        total_duration_ms=result.get("total_duration_ms"),
    )
