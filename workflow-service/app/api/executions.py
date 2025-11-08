from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from ..core.database import get_db
from ..services.dependencies import TokenClaims, validate_token, validate_token_or_api_key
from ..services.execution_service import ExecutionService
from ..core.exceptions import (
    WorkflowExecutionError, StepExecutionError, WorkflowNotFoundError, WorkflowStateError
)
from ..schemas.execution_schema import (
    ExecutionStartRequest,
    ExecutionStepRequest,
    WorkflowExecutionResponse,
    ExecutionList,
    StepExecutionResult,
    WorkflowStateResponse
)

router = APIRouter()


@router.get("/", response_model=ExecutionList)
async def list_executions(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    workflow_id: str = None,
    status: str = None,
    db: Session = Depends(get_db),
    claims: TokenClaims = Depends(validate_token)
):
    """List workflow executions for the authenticated tenant"""
    try:
        service = ExecutionService(db)
        return service.list_executions(
            tenant_id=claims.tenant_id,
            page=page,
            size=size,
            workflow_id=workflow_id,
            status=status
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{execution_id}", response_model=WorkflowExecutionResponse)
async def get_execution(
    execution_id: str,
    db: Session = Depends(get_db),
    claims: TokenClaims = Depends(validate_token)
):
    """Get a specific workflow execution by ID"""
    try:
        service = ExecutionService(db)
        return await service.get_execution(execution_id, claims.tenant_id)
    except WorkflowExecutionError:
        raise HTTPException(status_code=404, detail="Execution not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/start", response_model=WorkflowExecutionResponse)
async def start_execution(
    request: ExecutionStartRequest,
    db: Session = Depends(get_db),
    claims: TokenClaims = Depends(validate_token_or_api_key)
):
    """Start a new workflow execution

    Authentication: Accepts either JWT Bearer token OR X-API-Key header
    """
    try:
        service = ExecutionService(db)
        return await service.start_execution(
            request=request,
            tenant_id=claims.tenant_id,
            user_identifier=claims.email or claims.user_id
        )
    except WorkflowNotFoundError:
        raise HTTPException(status_code=404, detail="Workflow not found")
    except WorkflowExecutionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/step", response_model=StepExecutionResult)
async def execute_step(
    request: ExecutionStepRequest,
    db: Session = Depends(get_db),
    claims: TokenClaims = Depends(validate_token_or_api_key)
):
    """Execute the next step in a workflow

    Authentication: Accepts either JWT Bearer token OR X-API-Key header
    """
    try:
        service = ExecutionService(db)
        return await service.execute_step(
            request=request,
            tenant_id=claims.tenant_id
        )
    except WorkflowExecutionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except StepExecutionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except WorkflowStateError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session/{session_id}/state", response_model=WorkflowStateResponse)
async def get_session_state(
    session_id: str,
    db: Session = Depends(get_db),
    claims: TokenClaims = Depends(validate_token_or_api_key)
):
    """Get the current workflow state for a session

    Authentication: Accepts either JWT Bearer token OR X-API-Key header
    """
    from ..core.logging_config import get_logger
    logger = get_logger("executions_api")

    try:
        from ..services.state_manager import StateManager
        state_manager = StateManager(db)
        state = await state_manager.get_state(session_id)

        if not state:
            logger.debug(f"Session state not found for session_id={session_id}")
            raise HTTPException(status_code=404, detail="Session state not found")

        # Verify tenant access
        if state.get("tenant_id") != claims.tenant_id:
            logger.warning(f"Access denied for session_id={session_id}, tenant_id mismatch")
            raise HTTPException(status_code=403, detail="Access denied")

        # Parse datetime strings to datetime objects
        from datetime import datetime
        created_at = datetime.fromisoformat(state["created_at"]) if state.get("created_at") else datetime.utcnow()
        updated_at = datetime.fromisoformat(state["updated_at"]) if state.get("updated_at") else datetime.utcnow()
        expires_at = datetime.fromisoformat(state["expires_at"]) if state.get("expires_at") else None

        return WorkflowStateResponse(
            session_id=state["session_id"],
            execution_id=state["execution_id"],
            workflow_id=state["workflow_id"],
            current_step_id=state["current_step_id"],
            step_context=state.get("step_context", {}),
            variables=state.get("variables", {}),
            waiting_for_input=state.get("waiting_for_input"),
            last_user_message=state.get("last_user_message"),
            last_bot_message=state.get("last_bot_message"),
            created_at=created_at,
            updated_at=updated_at,
            expires_at=expires_at
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get session state for session_id={session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{execution_id}/cancel")
async def cancel_execution(
    execution_id: str,
    db: Session = Depends(get_db),
    claims: TokenClaims = Depends(validate_token)
):
    """Cancel a running workflow execution"""
    try:
        service = ExecutionService(db)
        success = await service.cancel_execution(execution_id, claims.tenant_id)
        if success:
            return {"message": "Execution cancelled successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to cancel execution")
    except WorkflowExecutionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))