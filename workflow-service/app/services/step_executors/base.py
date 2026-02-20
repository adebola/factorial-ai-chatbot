"""
Base Step Executor - Abstract Interface

Defines the contract that all step executors must implement.
This enables the Strategy pattern for clean, maintainable workflow execution.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple, Optional
from ...schemas.workflow_schema import WorkflowStep, WorkflowDefinition, StepType
from ...schemas.execution_schema import StepExecutionResult, FALLBACK_TO_AI_SENTINEL
from ..workflow_parser import WorkflowParser


class StepExecutor(ABC):
    """
    Abstract base class for step executors.

    Each concrete executor implements execute() for a specific step type.
    This eliminates the need for giant if-else chains in execution logic.
    """

    @property
    @abstractmethod
    def step_type(self) -> StepType:
        """Return the step type this executor handles"""
        pass

    @abstractmethod
    async def execute(
        self,
        step: WorkflowStep,
        variables: Dict[str, Any],
        definition: WorkflowDefinition,
        execution_context: Dict[str, Any]
    ) -> StepExecutionResult:
        """
        Execute a workflow step.

        Args:
            step: The workflow step to execute
            variables: Current workflow variables
            definition: Full workflow definition (for next step lookups)
            execution_context: Execution metadata (tenant_id, execution_id, etc.)

        Returns:
            StepExecutionResult with execution outcome

        Raises:
            StepExecutionError: If execution fails
        """
        pass

    def is_interactive(self) -> bool:
        """
        Check if this step type requires user interaction.

        Interactive steps (MESSAGE, CHOICE, INPUT) pause auto-execution.
        Non-interactive steps (CONDITION, ACTION) execute automatically.

        Returns:
            True if step requires user interaction, False otherwise
        """
        return self.step_type in [
            StepType.MESSAGE,
            StepType.CHOICE,
            StepType.INPUT
        ]

    def _resolve_next_step(
        self,
        next_step_id: Optional[str],
        definition: WorkflowDefinition
    ) -> Tuple[Optional[str], bool, bool]:
        """
        Centralized next-step resolution for all executors.

        Returns:
            (resolved_next_step_id, workflow_completed, fallback_to_ai)
        """
        if not next_step_id:
            return None, True, False
        if next_step_id == FALLBACK_TO_AI_SENTINEL:
            return None, True, True
        if not WorkflowParser.get_step_by_id(definition, next_step_id):
            return None, True, False
        return next_step_id, False, False
