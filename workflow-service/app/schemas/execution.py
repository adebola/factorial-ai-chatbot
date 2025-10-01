from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum


class ExecutionStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class StepType(str, Enum):
    MESSAGE = "message"
    CHOICE = "choice"
    INPUT = "input"
    CONDITION = "condition"
    ACTION = "action"
    SUB_WORKFLOW = "sub_workflow"
    DELAY = "delay"


# Execution Request Schemas
class ExecutionStartRequest(BaseModel):
    workflow_id: str
    session_id: str
    user_identifier: Optional[str] = None
    initial_variables: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None


class ExecutionStepRequest(BaseModel):
    execution_id: str
    session_id: str
    user_input: Optional[str] = None
    user_choice: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class ExecutionUpdateRequest(BaseModel):
    status: Optional[ExecutionStatus] = None
    variables: Optional[Dict[str, Any]] = None
    current_step_id: Optional[str] = None


# Execution Response Schemas
class StepExecutionResponse(BaseModel):
    id: str
    step_id: str
    step_type: StepType
    status: ExecutionStatus
    input_data: Optional[Dict[str, Any]]
    output_data: Optional[Dict[str, Any]]
    error_message: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]
    duration_ms: Optional[int]

    class Config:
        from_attributes = True


class WorkflowExecutionResponse(BaseModel):
    id: str
    workflow_id: str
    tenant_id: str
    session_id: str
    user_identifier: Optional[str]
    status: ExecutionStatus
    current_step_id: Optional[str]
    variables: Dict[str, Any]
    started_at: datetime
    completed_at: Optional[datetime]
    error_message: Optional[str]
    steps_completed: int
    total_steps: Optional[int]

    class Config:
        from_attributes = True


class WorkflowStateResponse(BaseModel):
    session_id: str
    execution_id: str
    workflow_id: str
    current_step_id: str
    step_context: Dict[str, Any]
    variables: Dict[str, Any]
    waiting_for_input: Optional[str]
    last_user_message: Optional[str]
    last_bot_message: Optional[str]
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime]

    class Config:
        from_attributes = True


# Step Execution Response for Chat Integration
class StepExecutionResult(BaseModel):
    """Result of executing a workflow step"""
    success: bool
    step_id: str
    step_type: StepType

    # Response to send to user
    message: Optional[str] = None
    choices: Optional[List[str]] = None
    input_required: Optional[str] = None  # Type of input expected

    # Workflow state
    next_step_id: Optional[str] = None
    workflow_completed: bool = False
    variables_updated: Optional[Dict[str, Any]] = None

    # Error handling
    error_message: Optional[str] = None
    fallback_to_ai: bool = False

    # Metadata
    metadata: Optional[Dict[str, Any]] = None


# Analytics Schemas
class WorkflowAnalyticsResponse(BaseModel):
    workflow_id: str
    date: datetime
    total_executions: int
    completed_executions: int
    failed_executions: int
    avg_completion_time_ms: Optional[int]
    avg_steps_completed: Optional[int]
    completion_rate: Optional[int]
    unique_users: int
    returning_users: int

    class Config:
        from_attributes = True


class WorkflowMetrics(BaseModel):
    """Aggregated workflow metrics"""
    total_workflows: int
    active_workflows: int
    total_executions: int
    avg_completion_rate: float
    top_workflows: List[Dict[str, Any]]
    recent_activity: List[Dict[str, Any]]


# Execution List Schemas
class ExecutionSummary(BaseModel):
    id: str
    workflow_id: str
    session_id: str
    user_identifier: Optional[str]
    status: ExecutionStatus
    steps_completed: int
    total_steps: Optional[int]
    started_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class ExecutionList(BaseModel):
    executions: List[ExecutionSummary]
    total: int
    page: int
    size: int