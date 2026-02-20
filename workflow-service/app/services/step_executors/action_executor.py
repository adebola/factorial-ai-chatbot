"""
Action Step Executor

Executes ACTION steps - performs actions like send_email, api_call, log.
Delegates to ActionService which routes to the appropriate ActionHandler.
"""

from typing import Dict, Any
from sqlalchemy.orm import Session
from .base import StepExecutor
from ...schemas.workflow_schema import WorkflowStep, WorkflowDefinition, StepType
from ...schemas.execution_schema import StepExecutionResult
from ..action_service import ActionService
from ...core.exceptions import StepExecutionError
from ...core.logging_config import get_logger

logger = get_logger("action_executor")


class ActionStepExecutor(StepExecutor):
    """Executor for ACTION type steps"""

    def __init__(self, db: Session = None):
        self.db = db
        self._action_service = None

    def _get_action_service(self) -> ActionService:
        """Lazy-initialize ActionService"""
        if self._action_service is None:
            self._action_service = ActionService(db=self.db)
        return self._action_service

    @property
    def step_type(self) -> StepType:
        return StepType.ACTION

    def is_interactive(self) -> bool:
        """ACTION steps are non-interactive and execute automatically"""
        return False

    async def execute(
        self,
        step: WorkflowStep,
        variables: Dict[str, Any],
        definition: WorkflowDefinition,
        execution_context: Dict[str, Any]
    ) -> StepExecutionResult:
        """
        Execute ACTION step.

        ACTION steps perform operations like:
        - send_email: Send emails via RabbitMQ
        - api_call: POST to external APIs
        - log: Log information during workflow execution
        """
        if not step.action:
            raise StepExecutionError(step.id, "Action step missing action type")

        logger.info(
            "Executing ACTION step",
            step_id=step.id,
            step_name=step.name,
            action_type=step.action,
            execution_id=execution_context.get("execution_id")
        )

        # Execute the action via ActionService
        # ActionService handles variable resolution and action dispatching
        action_service = self._get_action_service()
        action_result = await action_service.execute_action(
            action_type=step.action,
            action_params=step.params or {},
            variables=variables,
            tenant_id=execution_context.get("tenant_id"),
            execution_id=execution_context.get("execution_id")
        )

        logger.info(
            "ACTION completed",
            step_id=step.id,
            action_type=step.action,
            action_success=action_result.get("success"),
            execution_id=execution_context.get("execution_id")
        )

        # Determine next step and workflow completion
        resolved_id, workflow_completed, fallback_to_ai = self._resolve_next_step(
            step.next_step, definition
        )

        if workflow_completed:
            variables["__workflow_completed"] = True
            logger.info(
                "ACTION step completes workflow",
                step_id=step.id,
                action_type=step.action,
                next_step=step.next_step,
                fallback_to_ai=fallback_to_ai,
                execution_id=execution_context.get("execution_id")
            )

        # Build success message
        action_type = step.action
        if action_type == "send_email":
            message = f"Email sent to {action_result.get('recipient', 'unknown')}"
        elif action_type == "api_call":
            message = f"API call completed: POST {action_result.get('url', 'unknown')} (status {action_result.get('status_code', '?')})"
        else:
            message = f"Action '{action_type}' completed successfully"

        return StepExecutionResult(
            success=action_result.get("success", False),
            step_id=step.id,
            step_type=self.step_type,
            message=message,
            next_step_id=resolved_id,
            workflow_completed=workflow_completed,
            fallback_to_ai=fallback_to_ai,
            input_required=None,
            workflow_id=execution_context.get("workflow_id"),
            metadata={
                "action_type": step.action,
                "action_result": action_result
            }
        )
