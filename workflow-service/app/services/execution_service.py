"""
Execution service for running workflows.
Handles the complete lifecycle of workflow execution.
"""
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime
from sqlalchemy.orm import Session

from ..models.workflow import Workflow
from ..models.execution import (
    WorkflowExecution, StepExecution, ExecutionStatus, StepType
)
from ..schemas.execution import (
    ExecutionStartRequest, ExecutionStepRequest, StepExecutionResult,
    WorkflowExecutionResponse, ExecutionSummary, ExecutionList
)
from ..schemas.workflow import StepType as SchemaStepType
from ..core.exceptions import (
    WorkflowExecutionError, StepExecutionError, WorkflowNotFoundError, WorkflowStateError
)
from ..core.logging_config import get_logger
from .workflow_parser import WorkflowParser
from .variable_resolver import VariableResolver
from .action_service import ActionService
from .state_manager import StateManager

logger = get_logger("execution_service")


class ExecutionService:
    """Service for executing workflows"""

    def __init__(self, db: Session):
        self.db = db
        self.action_service = ActionService()
        self.state_manager = StateManager(db)

    async def start_execution(
        self,
        request: ExecutionStartRequest,
        tenant_id: str,
        user_identifier: Optional[str] = None
    ) -> WorkflowExecutionResponse:
        """
        Start a new workflow execution.

        Args:
            request: Execution start request
            tenant_id: Tenant ID
            user_identifier: Optional user identifier

        Returns:
            Workflow execution response
        """
        try:
            # Get the workflow
            workflow = self.db.query(Workflow).filter(
                Workflow.id == request.workflow_id,
                Workflow.tenant_id == tenant_id
            ).first()

            if not workflow:
                raise WorkflowNotFoundError(f"Workflow {request.workflow_id} not found")

            if not workflow.is_active:
                raise WorkflowExecutionError("Cannot execute inactive workflow")

            # Parse workflow definition
            definition = WorkflowParser.parse_from_dict(workflow.definition)

            # Get first step
            first_step = WorkflowParser.get_first_step(definition)
            if not first_step:
                raise WorkflowExecutionError("Workflow has no steps")

            # Initialize variables
            variables = VariableResolver.merge_variables(
                definition.variables or {},
                request.initial_variables or {},
                request.context or {}
            )
            variables = VariableResolver.add_system_variables(variables)

            # Create execution record
            execution = WorkflowExecution(
                id=str(uuid.uuid4()),
                workflow_id=workflow.id,
                tenant_id=tenant_id,
                session_id=request.session_id,
                user_identifier=user_identifier,
                status=ExecutionStatus.RUNNING,
                current_step_id=first_step.id,
                variables=variables,
                total_steps=len(definition.steps)
            )

            self.db.add(execution)
            self.db.commit()
            self.db.refresh(execution)

            # Save initial state
            await self.state_manager.save_state(
                session_id=request.session_id,
                execution_id=execution.id,
                workflow_id=workflow.id,
                tenant_id=tenant_id,
                current_step_id=first_step.id,
                variables=variables
            )

            # Update workflow usage
            workflow.usage_count += 1
            workflow.last_used_at = datetime.utcnow()
            self.db.commit()

            logger.info(f"Started workflow execution {execution.id} for workflow {workflow.id}")

            # Execute the first step if it's not waiting for input
            if first_step.type != SchemaStepType.INPUT and first_step.type != SchemaStepType.CHOICE:
                await self._execute_step_internal(execution, first_step, definition, variables)

            return self._to_execution_response(execution)

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to start execution: {e}")
            raise

    async def execute_step(
        self,
        request: ExecutionStepRequest,
        tenant_id: str
    ) -> StepExecutionResult:
        """
        Execute the next step in a workflow.

        Args:
            request: Step execution request
            tenant_id: Tenant ID

        Returns:
            Step execution result
        """
        try:
            # Get execution
            execution = self.db.query(WorkflowExecution).filter(
                WorkflowExecution.id == request.execution_id,
                WorkflowExecution.tenant_id == tenant_id
            ).first()

            if not execution:
                raise WorkflowExecutionError(f"Execution {request.execution_id} not found")

            if execution.status != ExecutionStatus.RUNNING:
                raise WorkflowExecutionError(f"Execution is not running (status: {execution.status})")

            # Get workflow and definition
            workflow = self.db.query(Workflow).filter(
                Workflow.id == execution.workflow_id
            ).first()

            if not workflow:
                raise WorkflowNotFoundError(f"Workflow {execution.workflow_id} not found")

            definition = WorkflowParser.parse_from_dict(workflow.definition)

            # Get current step
            current_step = WorkflowParser.get_step_by_id(definition, execution.current_step_id)
            if not current_step:
                raise StepExecutionError(execution.current_step_id, "Step not found in workflow definition")

            # Get current variables from state
            state = await self.state_manager.get_state(request.session_id)
            if not state:
                raise WorkflowStateError(f"No state found for session {request.session_id}")

            variables = state.get("variables", {})

            # Process user input if provided
            if request.user_input:
                variables = self._process_user_input(current_step, request.user_input, variables)

            if request.user_choice:
                variables = self._process_user_choice(current_step, request.user_choice, variables)

            # Update context if provided
            if request.context:
                variables = VariableResolver.merge_variables(variables, request.context)

            # Execute the step
            result = await self._execute_step_internal(execution, current_step, definition, variables)

            # Update execution progress
            execution.steps_completed += 1
            self.db.commit()

            return result

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to execute step: {e}")
            raise

    async def cancel_execution(self, execution_id: str, tenant_id: str) -> bool:
        """
        Cancel a running workflow execution.

        Args:
            execution_id: Execution ID
            tenant_id: Tenant ID

        Returns:
            True if cancelled successfully
        """
        try:
            execution = self.db.query(WorkflowExecution).filter(
                WorkflowExecution.id == execution_id,
                WorkflowExecution.tenant_id == tenant_id
            ).first()

            if not execution:
                raise WorkflowExecutionError(f"Execution {execution_id} not found")

            if execution.status != ExecutionStatus.RUNNING:
                raise WorkflowExecutionError(f"Cannot cancel execution with status: {execution.status}")

            # Update execution status
            execution.status = ExecutionStatus.CANCELLED
            execution.completed_at = datetime.utcnow()

            self.db.commit()

            # Clean up state
            await self.state_manager.delete_state(execution.session_id)

            logger.info(f"Cancelled execution {execution_id}")
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to cancel execution {execution_id}: {e}")
            raise

    async def get_execution(self, execution_id: str, tenant_id: str) -> WorkflowExecutionResponse:
        """
        Get execution details.

        Args:
            execution_id: Execution ID
            tenant_id: Tenant ID

        Returns:
            Execution response
        """
        execution = self.db.query(WorkflowExecution).filter(
            WorkflowExecution.id == execution_id,
            WorkflowExecution.tenant_id == tenant_id
        ).first()

        if not execution:
            raise WorkflowExecutionError(f"Execution {execution_id} not found")

        return self._to_execution_response(execution)

    def list_executions(
        self,
        tenant_id: str,
        page: int = 1,
        size: int = 10,
        workflow_id: Optional[str] = None,
        status: Optional[str] = None
    ) -> ExecutionList:
        """
        List workflow executions for a tenant.

        Args:
            tenant_id: Tenant ID
            page: Page number
            size: Page size
            workflow_id: Filter by workflow ID
            status: Filter by status

        Returns:
            Paginated execution list
        """
        query = self.db.query(WorkflowExecution).filter(
            WorkflowExecution.tenant_id == tenant_id
        )

        if workflow_id:
            query = query.filter(WorkflowExecution.workflow_id == workflow_id)
        if status:
            query = query.filter(WorkflowExecution.status == status)

        total = query.count()

        offset = (page - 1) * size
        executions = query.order_by(WorkflowExecution.started_at.desc()).offset(offset).limit(size).all()

        execution_summaries = [self._to_execution_summary(e) for e in executions]

        return ExecutionList(
            executions=execution_summaries,
            total=total,
            page=page,
            size=size
        )

    async def _execute_step_internal(
        self,
        execution: WorkflowExecution,
        step,
        definition,
        variables: Dict[str, Any]
    ) -> StepExecutionResult:
        """Execute a single workflow step"""
        step_start_time = datetime.utcnow()

        try:
            # Create step execution record
            step_execution = StepExecution(
                id=str(uuid.uuid4()),
                execution_id=execution.id,
                workflow_id=execution.workflow_id,
                tenant_id=execution.tenant_id,
                step_id=step.id,
                step_type=StepType(step.type.value),
                step_config=step.model_dump(),
                input_data=variables,
                status=ExecutionStatus.RUNNING
            )

            self.db.add(step_execution)
            self.db.commit()

            # Execute based on step type
            if step.type == SchemaStepType.MESSAGE:
                result = await self._execute_message_step(step, variables)
            elif step.type == SchemaStepType.CHOICE:
                result = await self._execute_choice_step(step, variables)
            elif step.type == SchemaStepType.INPUT:
                result = await self._execute_input_step(step, variables)
            elif step.type == SchemaStepType.CONDITION:
                result = await self._execute_condition_step(step, variables, definition)
            elif step.type == SchemaStepType.ACTION:
                result = await self._execute_action_step(step, variables, execution)
            elif step.type == SchemaStepType.DELAY:
                result = await self._execute_delay_step(step, variables)
            else:
                raise StepExecutionError(step.id, f"Unsupported step type: {step.type}")

            # Update step execution record
            step_execution.status = ExecutionStatus.COMPLETED
            step_execution.output_data = result
            step_execution.completed_at = datetime.utcnow()
            step_execution.duration_ms = int(
                (step_execution.completed_at - step_start_time).total_seconds() * 1000
            )

            # Update execution state
            if result.get("next_step_id"):
                execution.current_step_id = result["next_step_id"]
                await self.state_manager.advance_step(
                    execution.session_id,
                    result["next_step_id"],
                    waiting_for_input=result.get("waiting_for_input")
                )
            elif result.get("workflow_completed"):
                execution.status = ExecutionStatus.COMPLETED
                execution.completed_at = datetime.utcnow()
                await self.state_manager.delete_state(execution.session_id)

            # Update variables if changed
            if result.get("variables_updated"):
                variables.update(result["variables_updated"])
                execution.variables = variables
                await self.state_manager.update_variables(execution.session_id, variables)

            self.db.commit()

            logger.debug(f"Executed step {step.id} in execution {execution.id}")

            return StepExecutionResult(
                success=True,
                step_id=step.id,
                step_type=step.type,
                message=result.get("message"),
                choices=result.get("choices"),
                input_required=result.get("input_required"),
                next_step_id=result.get("next_step_id"),
                workflow_completed=result.get("workflow_completed", False),
                variables_updated=result.get("variables_updated"),
                metadata=result.get("metadata")
            )

        except Exception as e:
            # Update step execution record with error
            step_execution.status = ExecutionStatus.FAILED
            step_execution.error_message = str(e)
            step_execution.completed_at = datetime.utcnow()

            # Mark execution as failed
            execution.status = ExecutionStatus.FAILED
            execution.error_message = str(e)
            execution.completed_at = datetime.utcnow()

            self.db.commit()

            logger.error(f"Step execution failed: {e}")
            raise StepExecutionError(step.id, str(e))

    async def _execute_message_step(self, step, variables: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a message step"""
        message = VariableResolver.resolve_content(step.content, variables)

        return {
            "message": message,
            "next_step_id": step.next_step,
            "workflow_completed": step.next_step is None
        }

    async def _execute_choice_step(self, step, variables: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a choice step"""
        message = VariableResolver.resolve_content(step.content, variables)
        choices = [VariableResolver.resolve_content(choice, variables) for choice in step.options or []]

        return {
            "message": message,
            "choices": choices,
            "input_required": "choice",
            "waiting_for_input": "choice"
        }

    async def _execute_input_step(self, step, variables: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an input step"""
        message = VariableResolver.resolve_content(step.content, variables)

        return {
            "message": message,
            "input_required": "text",
            "waiting_for_input": "text"
        }

    async def _execute_condition_step(self, step, variables: Dict[str, Any], definition) -> Dict[str, Any]:
        """Execute a condition step"""
        if not step.condition:
            raise StepExecutionError(step.id, "Condition step missing condition expression")

        condition_result = VariableResolver.evaluate_condition(step.condition, variables)

        if condition_result:
            next_step_id = step.next_step
        else:
            # Look for an alternate path or end workflow
            next_step_id = None  # Could implement else_step logic here

        return {
            "condition_result": condition_result,
            "next_step_id": next_step_id,
            "workflow_completed": next_step_id is None
        }

    async def _execute_action_step(self, step, variables: Dict[str, Any], execution) -> Dict[str, Any]:
        """Execute an action step"""
        if not step.action:
            raise StepExecutionError(step.id, "Action step missing action type")

        # Execute the action
        action_result = await self.action_service.execute_action(
            action_type=step.action,
            action_params=step.params or {},
            variables=variables,
            tenant_id=execution.tenant_id,
            execution_id=execution.id
        )

        return {
            "action_result": action_result,
            "next_step_id": step.next_step,
            "workflow_completed": step.next_step is None
        }

    async def _execute_delay_step(self, step, variables: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a delay step"""
        # For now, just continue to next step
        # In production, this would schedule continuation
        return {
            "delay_processed": True,
            "next_step_id": step.next_step,
            "workflow_completed": step.next_step is None
        }

    def _process_user_input(self, step, user_input: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        """Process user input for input steps"""
        if step.variable:
            # Extract variables from user input
            extracted_vars = VariableResolver.extract_variables_from_text(user_input, step.variable)
            variables = VariableResolver.merge_variables(variables, extracted_vars)

        return variables

    def _process_user_choice(self, step, user_choice: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        """Process user choice for choice steps"""
        if step.variable:
            variables = VariableResolver.set_variable(variables, step.variable, user_choice)

        return variables

    def _to_execution_response(self, execution: WorkflowExecution) -> WorkflowExecutionResponse:
        """Convert execution model to response"""
        return WorkflowExecutionResponse(
            id=execution.id,
            workflow_id=execution.workflow_id,
            tenant_id=execution.tenant_id,
            session_id=execution.session_id,
            user_identifier=execution.user_identifier,
            status=execution.status,
            current_step_id=execution.current_step_id,
            variables=execution.variables or {},
            started_at=execution.started_at,
            completed_at=execution.completed_at,
            error_message=execution.error_message,
            steps_completed=execution.steps_completed,
            total_steps=execution.total_steps
        )

    def _to_execution_summary(self, execution: WorkflowExecution) -> ExecutionSummary:
        """Convert execution model to summary"""
        return ExecutionSummary(
            id=execution.id,
            workflow_id=execution.workflow_id,
            session_id=execution.session_id,
            user_identifier=execution.user_identifier,
            status=execution.status,
            steps_completed=execution.steps_completed,
            total_steps=execution.total_steps,
            started_at=execution.started_at,
            completed_at=execution.completed_at
        )