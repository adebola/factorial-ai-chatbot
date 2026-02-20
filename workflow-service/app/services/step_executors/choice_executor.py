"""
Choice Step Executor

Executes CHOICE steps - presents options to user and branches based on selection.

BUG FIX: This executor fixes state pollution from temporary flags.
The old code created flags like __choice_made and __choice_step_completed_{step_id}
but didn't always clean them up, causing inconsistent workflow behavior.
"""

from typing import Dict, Any, List
from .base import StepExecutor
from ...schemas.workflow_schema import WorkflowStep, WorkflowDefinition, StepType
from ...schemas.execution_schema import StepExecutionResult
from ..variable_resolver import VariableResolver
from ...core.logging_config import get_logger

logger = get_logger("choice_executor")


class ChoiceStepExecutor(StepExecutor):
    """Executor for CHOICE type steps"""

    @property
    def step_type(self) -> StepType:
        return StepType.CHOICE

    async def execute(
        self,
        step: WorkflowStep,
        variables: Dict[str, Any],
        definition: WorkflowDefinition,
        execution_context: Dict[str, Any]
    ) -> StepExecutionResult:
        """
        Execute CHOICE step.

        CHOICE steps present options to the user. Execution flow:
        1. Check if user just made a choice (temporary flags present)
        2. Check if choice was already made previously (variable set)
        3. Present choices and wait for user input

        FIXES:
        1. ✅ Clears temporary flags after use (prevents state pollution)
        2. ✅ Validates next_step exists (prevents stuck workflows)
        3. ✅ Returns input_required="choice" only when waiting
        """
        logger.info(
            "Executing CHOICE step",
            step_id=step.id,
            step_name=step.name,
            variable=step.variable,
            execution_id=execution_context.get("execution_id")
        )

        # Check if user just made a choice (from current request)
        if self._is_choice_just_made(step, variables):
            return self._process_just_made_choice(step, variables, definition, execution_context)

        # Check if choice was already completed in previous execution
        if self._is_choice_already_completed(step, variables):
            return self._process_already_completed_choice(step, variables, definition, execution_context)

        # No choice yet - present options
        return self._present_choices(step, variables, execution_context)

    def _is_choice_just_made(self, step: WorkflowStep, variables: Dict[str, Any]) -> bool:
        """Check if user just made a choice in this execution"""
        return (
            '__selected_option_next_step' in variables or
            '__choice_made' in variables
        )

    def _is_choice_already_completed(self, step: WorkflowStep, variables: Dict[str, Any]) -> bool:
        """Check if choice was completed in a previous execution"""
        # Check if we have the completion flag
        completion_flag = f'__choice_step_completed_{step.id}'
        if completion_flag in variables:
            return True

        # Or check if variable is already set (backward compatibility)
        if step.variable and step.variable in variables:
            value = variables.get(step.variable)
            # Non-empty value means choice was made
            return value is not None and value != ""

        return False

    def _process_just_made_choice(
        self,
        step: WorkflowStep,
        variables: Dict[str, Any],
        definition: WorkflowDefinition,
        execution_context: Dict[str, Any]
    ) -> StepExecutionResult:
        """
        Process a choice that was just made in this execution.

        CRITICAL: Cleans up temporary flags to prevent state pollution!
        """
        # Check for option-specific next_step (highest priority)
        selected_option_next_step = variables.get('__selected_option_next_step')

        if selected_option_next_step:
            # Clean up flag immediately! (THIS WAS MISSING IN OLD CODE)
            variables.pop('__selected_option_next_step', None)
            variables.pop('__choice_made', None)  # Clean up both flags

            logger.info(
                "CHOICE completed with option-specific next_step",
                step_id=step.id,
                next_step_id=selected_option_next_step,
                execution_id=execution_context.get("execution_id")
            )

            return self._advance_to_next_step(
                step, selected_option_next_step, definition, execution_context
            )

        # Choice made but no option-specific next_step, use step-level next_step
        if '__choice_made' in variables:
            variables.pop('__choice_made', None)  # Clean up flag!

            logger.info(
                "CHOICE completed with step-level next_step",
                step_id=step.id,
                next_step_id=step.next_step,
                execution_id=execution_context.get("execution_id")
            )

            return self._advance_to_next_step(
                step, step.next_step, definition, execution_context
            )

        # This shouldn't happen, but handle gracefully
        logger.warning(
            "CHOICE marked as made but no flags found",
            step_id=step.id,
            execution_id=execution_context.get("execution_id")
        )
        return self._present_choices(step, variables, execution_context)

    def _process_already_completed_choice(
        self,
        step: WorkflowStep,
        variables: Dict[str, Any],
        definition: WorkflowDefinition,
        execution_context: Dict[str, Any]
    ) -> StepExecutionResult:
        """
        Process a choice that was completed in a previous execution.

        This handles workflow resumption where choice was already made.
        """
        # Clean up completion flag (OLD CODE LEFT THIS FOREVER!)
        completion_flag = f'__choice_step_completed_{step.id}'
        variables.pop(completion_flag, None)

        logger.info(
            "CHOICE already completed (previous execution)",
            step_id=step.id,
            variable=step.variable,
            value=variables.get(step.variable) if step.variable else None,
            execution_id=execution_context.get("execution_id")
        )

        # Find the option that matches the stored value
        selected_next_step = None
        if step.variable and step.options:
            user_choice_value = variables.get(step.variable)
            for option in step.options:
                if option.value == user_choice_value or option.text == user_choice_value:
                    selected_next_step = option.next_step
                    logger.info(
                        "Found matching option for previous choice",
                        step_id=step.id,
                        option_value=option.value,
                        next_step=selected_next_step,
                        execution_id=execution_context.get("execution_id")
                    )
                    break

        # Use option's next_step if found, otherwise use step-level next_step
        next_step_id = selected_next_step if selected_next_step else step.next_step

        return self._advance_to_next_step(
            step, next_step_id, definition, execution_context
        )

    def _present_choices(
        self,
        step: WorkflowStep,
        variables: Dict[str, Any],
        execution_context: Dict[str, Any]
    ) -> StepExecutionResult:
        """Present choice options to user and wait for selection"""
        # Resolve message content
        message = VariableResolver.resolve_content(step.content or "", variables)

        # Build choices list
        choices = []
        if step.options:
            for option in step.options:
                choice_text = VariableResolver.resolve_content(option.text, variables)
                choices.append(choice_text)

        logger.info(
            "Presenting CHOICE options to user",
            step_id=step.id,
            num_choices=len(choices),
            execution_id=execution_context.get("execution_id")
        )

        return StepExecutionResult(
            success=True,
            step_id=step.id,
            step_type=self.step_type,
            message=message,
            choices=choices,
            input_required="choice",  # CRITICAL: Indicates waiting for choice
            next_step_id=None,  # Will be determined after choice is made
            workflow_completed=False,
            workflow_id=execution_context.get("workflow_id")
        )

    def _advance_to_next_step(
        self,
        step: WorkflowStep,
        next_step_id: str,
        definition: WorkflowDefinition,
        execution_context: Dict[str, Any]
    ) -> StepExecutionResult:
        """Advance to next step after choice is made"""
        resolved_id, workflow_completed, fallback_to_ai = self._resolve_next_step(
            next_step_id, definition
        )

        if workflow_completed:
            logger.info(
                "CHOICE completes workflow",
                step_id=step.id,
                next_step_id=next_step_id,
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
