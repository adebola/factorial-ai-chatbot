"""
Condition Step Executor

Executes CONDITION steps - evaluates a boolean expression and branches execution.

CONDITION steps are non-interactive and automatically proceed to the next step
if the condition is true, or complete the workflow if the condition is false.
"""

from typing import Dict, Any
from .base import StepExecutor
from ...schemas.workflow_schema import WorkflowStep, WorkflowDefinition, StepType
from ...schemas.execution_schema import StepExecutionResult
from ..variable_resolver import VariableResolver
from ...core.exceptions import StepExecutionError
from ...core.logging_config import get_logger

logger = get_logger("condition_executor")


class ConditionStepExecutor(StepExecutor):
    """Executor for CONDITION type steps"""

    @property
    def step_type(self) -> StepType:
        return StepType.CONDITION

    def is_interactive(self) -> bool:
        """CONDITION steps are non-interactive and execute automatically"""
        return False

    async def execute(
        self,
        step: WorkflowStep,
        variables: Dict[str, Any],
        definition: WorkflowDefinition,
        execution_context: Dict[str, Any]
    ) -> StepExecutionResult:
        """
        Execute CONDITION step.

        CONDITION steps evaluate a boolean expression using workflow variables.
        - If TRUE: proceed to next_step
        - If FALSE: workflow completes (could be extended to support else_step)
        """
        if not step.condition:
            raise StepExecutionError(step.id, "Condition step missing condition expression")

        # Evaluate condition expression
        condition_result = VariableResolver.evaluate_condition(step.condition, variables)

        logger.info(
            "Executing CONDITION step",
            step_id=step.id,
            step_name=step.name,
            condition=step.condition,
            result=condition_result,
            execution_id=execution_context.get("execution_id")
        )

        # Determine next step based on condition result
        fallback_to_ai = False
        if condition_result:
            resolved_id, workflow_completed, fallback_to_ai = self._resolve_next_step(
                step.next_step, definition
            )
            message = None

            logger.info(
                "CONDITION TRUE: proceeding",
                step_id=step.id,
                next_step_id=resolved_id,
                fallback_to_ai=fallback_to_ai,
                execution_id=execution_context.get("execution_id")
            )
        else:
            # Condition false - workflow ends
            resolved_id = None
            workflow_completed = True

            # Check metadata for fallback_to_ai flag on false branch
            if step.metadata and step.metadata.get("fallback_to_ai"):
                fallback_to_ai = True

            # Check for custom completion message in metadata
            message = None
            if step.metadata and "completion_message" in step.metadata:
                message = VariableResolver.resolve_content(
                    step.metadata["completion_message"],
                    variables
                )

            logger.info(
                "CONDITION FALSE: completing workflow",
                step_id=step.id,
                has_completion_message=bool(message),
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
            workflow_id=execution_context.get("workflow_id"),
            metadata={
                "condition": step.condition,
                "condition_result": condition_result
            }
        )
