"""
Input Step Executor

Executes INPUT steps - prompts user for text input and stores in variable.

INPUT steps collect free-form text from users and can optionally validate
the input before storing it in workflow variables.
"""

from typing import Dict, Any, Optional
from .base import StepExecutor
from ...schemas.workflow_schema import WorkflowStep, WorkflowDefinition, StepType
from ...schemas.execution_schema import StepExecutionResult
from ..variable_resolver import VariableResolver
from ...core.logging_config import get_logger

logger = get_logger("input_executor")


class InputStepExecutor(StepExecutor):
    """Executor for INPUT type steps"""

    @property
    def step_type(self) -> StepType:
        return StepType.INPUT

    async def execute(
        self,
        step: WorkflowStep,
        variables: Dict[str, Any],
        definition: WorkflowDefinition,
        execution_context: Dict[str, Any]
    ) -> StepExecutionResult:
        """
        Execute INPUT step.

        INPUT steps collect text from users. Execution flow:
        1. Check if input was already provided (variable is set)
        2. If not, present prompt and wait for input

        FEATURES:
        - ✅ Validates input exists before advancing
        - ✅ Supports optional validation rules (via metadata)
        - ✅ Properly completes workflow if no next_step
        """
        logger.info(
            "Executing INPUT step",
            step_id=step.id,
            step_name=step.name,
            variable=step.variable,
            execution_id=execution_context.get("execution_id")
        )

        # Check if input was already provided
        if self._is_input_provided(step, variables):
            return self._process_provided_input(step, variables, definition, execution_context)

        # No input yet - present prompt
        return self._present_input_prompt(step, variables, execution_context)

    def _is_input_provided(self, step: WorkflowStep, variables: Dict[str, Any]) -> bool:
        """Check if user has already provided input for this step"""
        if not step.variable:
            # No variable to store input - this is a configuration error
            # but we'll handle it gracefully by treating it as already provided
            logger.warning(
                "INPUT step has no variable defined",
                step_id=step.id
            )
            return True

        # Check if variable exists and has a non-empty value
        value = variables.get(step.variable)
        return value is not None and value != ""

    def _process_provided_input(
        self,
        step: WorkflowStep,
        variables: Dict[str, Any],
        definition: WorkflowDefinition,
        execution_context: Dict[str, Any]
    ) -> StepExecutionResult:
        """
        Process workflow after input has been provided.

        Input is already stored in variables by the ExecutionService
        when processing user_input. We just need to advance to next step.
        """
        input_value = variables.get(step.variable)

        logger.info(
            "INPUT already provided, advancing to next step",
            step_id=step.id,
            variable=step.variable,
            value_length=len(str(input_value)) if input_value else 0,
            execution_id=execution_context.get("execution_id")
        )

        # Optional: Validate input
        validation_error = self._validate_input(step, input_value)
        if validation_error:
            logger.warning(
                "INPUT validation failed",
                step_id=step.id,
                variable=step.variable,
                error=validation_error,
                execution_id=execution_context.get("execution_id")
            )
            # Return error and re-prompt for input
            return StepExecutionResult(
                success=False,
                step_id=step.id,
                step_type=self.step_type,
                message=validation_error,
                input_required="text",
                next_step_id=None,
                workflow_completed=False,
                error_message=validation_error,
                workflow_id=execution_context.get("workflow_id")
            )

        # Advance to next step
        return self._advance_to_next_step(step, definition, execution_context)

    def _present_input_prompt(
        self,
        step: WorkflowStep,
        variables: Dict[str, Any],
        execution_context: Dict[str, Any]
    ) -> StepExecutionResult:
        """Present input prompt to user and wait for input"""
        # Resolve prompt content
        message = VariableResolver.resolve_content(step.content or "", variables)

        logger.info(
            "Presenting INPUT prompt to user",
            step_id=step.id,
            variable=step.variable,
            execution_id=execution_context.get("execution_id")
        )

        return StepExecutionResult(
            success=True,
            step_id=step.id,
            step_type=self.step_type,
            message=message,
            input_required="text",  # CRITICAL: Indicates waiting for text input
            next_step_id=None,  # Will be determined after input is provided
            workflow_completed=False,
            workflow_id=execution_context.get("workflow_id")
        )

    def _advance_to_next_step(
        self,
        step: WorkflowStep,
        definition: WorkflowDefinition,
        execution_context: Dict[str, Any]
    ) -> StepExecutionResult:
        """Advance to next step after input is provided"""
        resolved_id, workflow_completed, fallback_to_ai = self._resolve_next_step(
            step.next_step, definition
        )

        if workflow_completed:
            logger.info(
                "INPUT completes workflow",
                step_id=step.id,
                next_step=step.next_step,
                fallback_to_ai=fallback_to_ai,
                execution_id=execution_context.get("execution_id")
            )

        return StepExecutionResult(
            success=True,
            step_id=step.id,
            step_type=self.step_type,
            next_step_id=resolved_id,
            workflow_completed=workflow_completed,
            fallback_to_ai=fallback_to_ai,
            input_required=None,
            workflow_id=execution_context.get("workflow_id")
        )

    def _validate_input(self, step: WorkflowStep, value: Any) -> Optional[str]:
        """
        Validate input value based on step metadata.

        Validation rules can be defined in step.metadata:
        - min_length: Minimum string length
        - max_length: Maximum string length
        - pattern: Regex pattern to match
        - required: Whether empty values are allowed

        Returns:
            Error message if validation fails, None if valid
        """
        if not step.metadata:
            return None  # No validation rules

        value_str = str(value) if value is not None else ""

        # Check required
        if step.metadata.get("required", False) and not value_str:
            return "Input is required. Please provide a value."

        # Check min_length
        min_length = step.metadata.get("min_length")
        if min_length and len(value_str) < min_length:
            return f"Input must be at least {min_length} characters long."

        # Check max_length
        max_length = step.metadata.get("max_length")
        if max_length and len(value_str) > max_length:
            return f"Input must be no more than {max_length} characters long."

        # Check pattern (regex)
        pattern = step.metadata.get("pattern")
        if pattern:
            import re
            if not re.match(pattern, value_str):
                error_msg = step.metadata.get("pattern_error", "Input does not match required format.")
                return error_msg

        return None  # Validation passed
