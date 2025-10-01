from sqlalchemy import Column, String, Text, DateTime, JSON, Enum as SQLEnum, Integer
from sqlalchemy.sql import func
import uuid
import enum
from datetime import datetime

from ..core.database import Base


class ExecutionStatus(enum.Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class StepType(enum.Enum):
    MESSAGE = "message"
    CHOICE = "choice"
    INPUT = "input"
    CONDITION = "condition"
    ACTION = "action"
    SUB_WORKFLOW = "sub_workflow"
    DELAY = "delay"


class WorkflowExecution(Base):
    """Tracks workflow execution instances"""
    __tablename__ = "workflow_executions"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    workflow_id = Column(String(36), nullable=False, index=True)
    tenant_id = Column(String(36), nullable=False, index=True)

    # Session context
    session_id = Column(String(36), nullable=False, index=True)  # Chat session ID
    user_identifier = Column(String(255), nullable=True)  # Email, phone, or user ID

    # Execution state
    status = Column(SQLEnum(ExecutionStatus), default=ExecutionStatus.RUNNING)
    current_step_id = Column(String(255), nullable=True)
    variables = Column(JSON, default=dict)  # Workflow variables and context

    # Execution metadata
    started_at = Column(DateTime, default=func.now(), nullable=False)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

    # Analytics
    steps_completed = Column(Integer, default=0)
    total_steps = Column(Integer, nullable=True)

    def __repr__(self):
        return f"<WorkflowExecution(id={self.id}, workflow_id={self.workflow_id}, status={self.status})>"


class WorkflowState(Base):
    """Current state of active workflow conversations"""
    __tablename__ = "workflow_states"

    session_id = Column(String(36), primary_key=True, index=True)  # Chat session ID
    execution_id = Column(String(36), nullable=False, index=True)
    workflow_id = Column(String(36), nullable=False, index=True)
    tenant_id = Column(String(36), nullable=False, index=True)

    # Current state
    current_step_id = Column(String(255), nullable=False)
    step_context = Column(JSON, default=dict)  # Step-specific context
    variables = Column(JSON, default=dict)  # Workflow variables

    # State management
    waiting_for_input = Column(String(100), nullable=True)  # Type of input expected
    last_user_message = Column(Text, nullable=True)
    last_bot_message = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    expires_at = Column(DateTime, nullable=True)  # When state expires

    def __repr__(self):
        return f"<WorkflowState(session_id={self.session_id}, current_step={self.current_step_id})>"


class StepExecution(Base):
    """Tracks individual step executions within workflows"""
    __tablename__ = "step_executions"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    execution_id = Column(String(36), nullable=False, index=True)
    workflow_id = Column(String(36), nullable=False, index=True)
    tenant_id = Column(String(36), nullable=False, index=True)

    # Step info
    step_id = Column(String(255), nullable=False)
    step_type = Column(SQLEnum(StepType), nullable=False)
    step_config = Column(JSON, nullable=True)  # Step configuration

    # Execution details
    input_data = Column(JSON, nullable=True)  # Input to the step
    output_data = Column(JSON, nullable=True)  # Output from the step
    status = Column(SQLEnum(ExecutionStatus), nullable=False)
    error_message = Column(Text, nullable=True)

    # Timing
    started_at = Column(DateTime, default=func.now(), nullable=False)
    completed_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)

    def __repr__(self):
        return f"<StepExecution(id={self.id}, step_id={self.step_id}, status={self.status})>"


class WorkflowAnalytics(Base):
    """Analytics and metrics for workflow performance"""
    __tablename__ = "workflow_analytics"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    workflow_id = Column(String(36), nullable=False, index=True)
    tenant_id = Column(String(36), nullable=False, index=True)

    # Aggregated metrics (daily)
    date = Column(DateTime, nullable=False)

    # Execution metrics
    total_executions = Column(Integer, default=0)
    completed_executions = Column(Integer, default=0)
    failed_executions = Column(Integer, default=0)

    # Performance metrics
    avg_completion_time_ms = Column(Integer, nullable=True)
    avg_steps_completed = Column(Integer, nullable=True)
    completion_rate = Column(Integer, nullable=True)  # Percentage

    # User engagement
    unique_users = Column(Integer, default=0)
    returning_users = Column(Integer, default=0)

    created_at = Column(DateTime, default=func.now(), nullable=False)

    def __repr__(self):
        return f"<WorkflowAnalytics(workflow_id={self.workflow_id}, date={self.date})>"