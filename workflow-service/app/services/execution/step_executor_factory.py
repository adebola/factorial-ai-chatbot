"""
Step Executor Factory

Factory pattern implementation for creating step executors.

ELIMINATES 23+ IF-ELSE CHAINS from old code by using a simple registry lookup.
This is a key part of fixing the bugs - single source of truth for executor selection.
"""

from typing import Dict, Optional
from ...schemas.workflow_schema import StepType
from ..step_executors.base import StepExecutor
from ..step_executors.message_executor import MessageStepExecutor
from ..step_executors.condition_executor import ConditionStepExecutor
from ..step_executors.choice_executor import ChoiceStepExecutor
from ..step_executors.input_executor import InputStepExecutor
from ..step_executors.action_executor import ActionStepExecutor
from ...core.exceptions import StepExecutionError
from ...core.logging_config import get_logger

logger = get_logger("step_executor_factory")


class StepExecutorFactory:
    """
    Factory for creating step executors based on step type.

    BEFORE (old code):
    ```python
    if step.type == StepType.MESSAGE:
        result = await self._execute_message_step(...)
    elif step.type == StepType.CHOICE:
        result = await self._execute_choice_step(...)
    elif step.type == StepType.INPUT:
        result = await self._execute_input_step(...)
    # ... 20 more lines of if-else
    ```

    AFTER (new code):
    ```python
    executor = StepExecutorFactory.create(step.type)
    result = await executor.execute(...)
    ```

    FIXES:
    1. ✅ Eliminates 23 if-else chains (source of bugs)
    2. ✅ Single registry = single source of truth
    3. ✅ Type-safe executor selection
    4. ✅ Easy to add new step types (just register executor)
    """

    # Executor registry - single source of truth
    _executors: Dict[StepType, StepExecutor] = {
        StepType.MESSAGE: MessageStepExecutor(),
        StepType.CHOICE: ChoiceStepExecutor(),
        StepType.INPUT: InputStepExecutor(),
        StepType.CONDITION: ConditionStepExecutor(),
        StepType.ACTION: ActionStepExecutor(),
    }

    @classmethod
    def create(cls, step_type: StepType) -> StepExecutor:
        """
        Get executor for the specified step type.

        Args:
            step_type: Type of step to execute

        Returns:
            Appropriate StepExecutor instance

        Raises:
            StepExecutionError: If step type is not supported
        """
        executor = cls._executors.get(step_type)

        if not executor:
            logger.error(
                "Unknown step type requested",
                step_type=step_type,
                available_types=[t.value for t in cls._executors.keys()]
            )
            raise StepExecutionError(
                step_id="unknown",
                message=f"Unknown step type: {step_type}. "
                        f"Available types: {[t.value for t in cls._executors.keys()]}"
            )

        logger.debug(
            "Created step executor",
            step_type=step_type,
            executor_class=executor.__class__.__name__
        )

        return executor

    @classmethod
    def register_executor(cls, step_type: StepType, executor: StepExecutor) -> None:
        """
        Register a new executor for a step type.

        This allows dynamic registration of executors, useful for:
        - Plugin systems
        - Custom step types
        - Testing with mock executors

        Args:
            step_type: Type of step
            executor: Executor instance to register
        """
        if step_type in cls._executors:
            logger.warning(
                "Overwriting existing executor",
                step_type=step_type,
                old_executor=cls._executors[step_type].__class__.__name__,
                new_executor=executor.__class__.__name__
            )

        cls._executors[step_type] = executor

        logger.info(
            "Registered step executor",
            step_type=step_type,
            executor_class=executor.__class__.__name__
        )

    @classmethod
    def get_supported_types(cls) -> list[StepType]:
        """
        Get list of supported step types.

        Returns:
            List of step types that have registered executors
        """
        return list(cls._executors.keys())

    @classmethod
    def is_supported(cls, step_type: StepType) -> bool:
        """
        Check if a step type is supported.

        Args:
            step_type: Type to check

        Returns:
            True if executor is registered for this type
        """
        return step_type in cls._executors

    @classmethod
    def is_interactive(cls, step_type: StepType) -> bool:
        """
        Check if a step type requires user interaction.

        This is a convenience method that delegates to the executor's
        is_interactive() method.

        Args:
            step_type: Type to check

        Returns:
            True if step type is interactive (MESSAGE, CHOICE, INPUT)

        Raises:
            StepExecutionError: If step type is not supported
        """
        executor = cls.create(step_type)
        return executor.is_interactive()
