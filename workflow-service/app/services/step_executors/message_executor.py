"""
Message Step Executor

Executes MESSAGE steps - displays a message to the user.

BUG FIX: This executor fixes the production bug where MESSAGE steps
were blocking workflow execution. The key fixes:
1. Always returns input_required=None (never blocks auto-execution)
2. Properly sets workflow_completed when next_step is None
3. Single implementation eliminates inconsistencies from duplicated logic
"""

from typing import Dict, Any
from .base import StepExecutor
from ...schemas.workflow_schema import WorkflowStep, WorkflowDefinition, StepType
from ...schemas.execution_schema import StepExecutionResult
from ..variable_resolver import VariableResolver
from ...core.logging_config import get_logger

logger = get_logger("message_executor")


class MessageStepExecutor(StepExecutor):
    """Executor for MESSAGE type steps"""

    @property
    def step_type(self) -> StepType:
        return StepType.MESSAGE

    async def execute(
        self,
        step: WorkflowStep,
        variables: Dict[str, Any],
        definition: WorkflowDefinition,
        execution_context: Dict[str, Any]
    ) -> StepExecutionResult:
        """
        Execute MESSAGE step.

        MESSAGE steps display content to the user and always auto-advance
        to the next step. They never require user input.

        FIXES:
        1. ✅ Always returns input_required=None (never blocks execution)
        2. ✅ Properly sets workflow_completed when next_step is None
        3. ✅ Single implementation (no duplicates = no inconsistencies)
        """
        # Resolve message content with variables
        message = VariableResolver.resolve_content(step.content or "", variables)

        logger.info(
            "Executing MESSAGE step",
            step_id=step.id,
            step_name=step.name,
            message_length=len(message),
            execution_id=execution_context.get("execution_id")
        )

        # Determine next step
        resolved_id, workflow_completed, fallback_to_ai = self._resolve_next_step(
            step.next_step, definition
        )

        if workflow_completed:
            variables["__workflow_completed"] = True
            logger.info(
                "MESSAGE step completes workflow",
                step_id=step.id,
                next_step=step.next_step,
                fallback_to_ai=fallback_to_ai,
                execution_id=execution_context.get("execution_id")
            )

        return StepExecutionResult(
            success=True,
            step_id=step.id,
            step_type=self.step_type,
            message=message,
            next_step_id=resolved_id,
            workflow_completed=workflow_completed,
            fallback_to_ai=fallback_to_ai,
            input_required=None,
            workflow_id=execution_context.get("workflow_id")
        )
