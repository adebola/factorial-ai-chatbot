"""
Unit Tests for WorkflowExecutor

Tests the auto-execution loop and step counter bug fix.

CRITICAL BUG FIX VERIFICATION:
1. Step counter increments ONCE per step (not 3+ times!)
2. Auto-execution continues through completed interactive steps
3. Auto-execution stops when step truly requires input
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime

from app.services.execution.workflow_executor import WorkflowExecutor
from app.models.execution_model import WorkflowExecution, ExecutionStatus
from app.schemas.workflow_schema import WorkflowStep, WorkflowDefinition, StepType
from app.schemas.execution_schema import StepExecutionResult


class TestWorkflowExecutor:
    """
    Test WorkflowExecutor auto-execution logic.

    CRITICAL BUG FIX: Step counter was incremented multiple times per step,
    causing 11/8 overflow. New executor increments ONCE per step.
    """

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        db = Mock()
        db.add = Mock()
        db.commit = Mock()
        db.refresh = Mock()
        return db

    @pytest.fixture
    def executor(self, mock_db):
        """Create WorkflowExecutor with mock database"""
        return WorkflowExecutor(mock_db)

    @pytest.fixture
    def mock_execution(self):
        """Mock WorkflowExecution database record"""
        return WorkflowExecution(
            id="test-exec-123",
            workflow_id="test-workflow",
            tenant_id="test-tenant",
            session_id="test-session",
            user_identifier="test-user",
            status=ExecutionStatus.RUNNING.value,
            steps_completed=0,
            total_steps=8,
            current_step_id="step1",
            variables={}
        )

    @pytest.mark.asyncio
    async def test_step_counter_increments_once_per_step(self, executor, mock_execution, mock_db):
        """
        CRITICAL BUG FIX TEST: Verify step counter increments ONCE per step.

        Old code incremented counter multiple times:
        - Line 721: steps_executed += 1
        - Line 736: execution.steps_completed += 1
        - Line 756: Another increment in some paths

        This caused 11/8 overflow bug. New code increments once.
        """
        # Create simple workflow: CONDITION -> CONDITION -> CONDITION (3 non-interactive steps)
        step1 = WorkflowStep(
            id="step1",
            name="Condition 1",
            type=StepType.CONDITION,
            condition="true",
            true_step="step2",
            false_step=None
        )
        step2 = WorkflowStep(
            id="step2",
            name="Condition 2",
            type=StepType.CONDITION,
            condition="true",
            true_step="step3",
            false_step=None
        )
        step3 = WorkflowStep(
            id="step3",
            name="Condition 3",
            type=StepType.CONDITION,
            condition="true",
            true_step=None,  # Final step
            false_step=None
        )

        mock_definition = Mock(spec=WorkflowDefinition)
        variables = {}

        # Mock WorkflowParser to return our steps
        with patch('app.services.execution.workflow_executor.WorkflowParser') as mock_parser:
            def get_step_side_effect(definition, step_id):
                step_map = {
                    "step1": step1,
                    "step2": step2,
                    "step3": step3
                }
                return step_map.get(step_id)

            mock_parser.get_step_by_id.side_effect = get_step_side_effect

            # Mock step execution to return success
            with patch.object(executor, 'execute_step') as mock_execute:
                async def execute_side_effect(execution, step, definition, variables):
                    # Return result that continues to next step
                    if step.id == "step1":
                        return StepExecutionResult(
                            success=True,
                            step_id="step1",
                            step_type=StepType.CONDITION,
                            next_step_id="step2",
                            workflow_completed=False,
                            input_required=None,
                            workflow_id="test-workflow"
                        )
                    elif step.id == "step2":
                        return StepExecutionResult(
                            success=True,
                            step_id="step2",
                            step_type=StepType.CONDITION,
                            next_step_id="step3",
                            workflow_completed=False,
                            input_required=None,
                            workflow_id="test-workflow"
                        )
                    else:  # step3
                        return StepExecutionResult(
                            success=True,
                            step_id="step3",
                            step_type=StepType.CONDITION,
                            next_step_id=None,
                            workflow_completed=True,
                            input_required=None,
                            workflow_id="test-workflow"
                        )

                mock_execute.side_effect = execute_side_effect

                # Execute workflow
                result = await executor.auto_execute_steps(
                    execution=mock_execution,
                    start_step_id="step1",
                    definition=mock_definition,
                    variables=variables,
                    max_steps=50
                )

                # BUG FIX VERIFICATION: Counter should be exactly 3, not 9 or 11!
                assert mock_execution.steps_completed == 3, \
                    f"Step counter must increment ONCE per step (was {mock_execution.steps_completed}, expected 3)"

                # Workflow should complete - check execution status
                assert mock_execution.status == ExecutionStatus.COMPLETED.value

    @pytest.mark.asyncio
    async def test_auto_execution_continues_through_completed_interactive(
        self, executor, mock_execution, mock_db
    ):
        """
        CRITICAL BUG FIX TEST: Auto-execution continues when interactive step is completed.

        This fixes the "AI typing forever" bug. When user completes a CHOICE step,
        auto-execution should continue to next step, not stop.

        OLD CODE:
        ```python
        if StepExecutorFactory.is_interactive(step.type):
            return result  # Stops even if choice completed!
        ```

        NEW CODE:
        ```python
        result = await execute_step(...)
        if result.input_required:  # Only stop if input actually needed
            return result
        ```
        """
        # Workflow: CHOICE (completed) -> MESSAGE -> ACTION
        choice_step = WorkflowStep(
            id="choice1",
            name="User Choice",
            type=StepType.CHOICE,
            content="Choose",
            options=[{"text": "opt1", "value": "Yes", "next_step": "msg1"}],
            next_step="msg1"
        )
        message_step = WorkflowStep(
            id="msg1",
            name="Confirmation",
            type=StepType.MESSAGE,
            content="Thank you!",
            next_step="action1"
        )
        action_step = WorkflowStep(
            id="action1",
            name="Send Email",
            type=StepType.ACTION,
            action="send_email",
            params={"to": "test@example.com"},
            next_step=None
        )

        mock_definition = Mock(spec=WorkflowDefinition)

        # User just completed choice
        variables = {
            "__choice_made": True,
            "__selected_option_next_step": "msg1"
        }

        with patch('app.services.execution.workflow_executor.WorkflowParser') as mock_parser:
            def get_step_side_effect(definition, step_id):
                step_map = {
                    "choice1": choice_step,
                    "msg1": message_step,
                    "action1": action_step
                }
                return step_map.get(step_id)

            mock_parser.get_step_by_id.side_effect = get_step_side_effect

            with patch.object(executor, 'execute_step') as mock_execute:
                async def execute_side_effect(execution, step, definition, variables):
                    if step.id == "choice1":
                        # Choice completed - no input required!
                        variables.pop("__choice_made", None)
                        variables.pop("__selected_option_next_step", None)
                        return StepExecutionResult(
                            success=True,
                            step_id="choice1",
                            step_type=StepType.CHOICE,
                            next_step_id="msg1",
                            workflow_completed=False,
                            input_required=None,  # Completed! No input needed
                            workflow_id="test-workflow"
                        )
                    elif step.id == "msg1":
                        return StepExecutionResult(
                            success=True,
                            step_id="msg1",
                            step_type=StepType.MESSAGE,
                            next_step_id="action1",
                            workflow_completed=False,
                            input_required=None,
                            workflow_id="test-workflow"
                        )
                    else:  # action1
                        return StepExecutionResult(
                            success=True,
                            step_id="action1",
                            step_type=StepType.ACTION,
                            next_step_id=None,
                            workflow_completed=True,
                            input_required=None,
                            workflow_id="test-workflow"
                        )

                mock_execute.side_effect = execute_side_effect

                # Execute from completed choice
                result = await executor.auto_execute_steps(
                    execution=mock_execution,
                    start_step_id="choice1",
                    definition=mock_definition,
                    variables=variables,
                    max_steps=50
                )

                # BUG FIX VERIFICATION: Should execute all 3 steps, not stop at choice!
                assert mock_execution.steps_completed == 3, \
                    "Auto-execution must continue through completed interactive steps"
                assert mock_execution.status == ExecutionStatus.COMPLETED.value

    @pytest.mark.asyncio
    async def test_auto_execution_stops_when_input_required(
        self, executor, mock_execution, mock_db
    ):
        """
        Verify auto-execution stops when step truly requires input.

        When CHOICE/INPUT step needs user input, auto-execution should stop
        and return that result for user interaction.
        """
        # Workflow: CONDITION -> CHOICE (waiting for input)
        condition_step = WorkflowStep(
            id="cond1",
            name="Check",
            type=StepType.CONDITION,
            condition="true",
            true_step="choice1",
            false_step=None
        )
        choice_step = WorkflowStep(
            id="choice1",
            name="User Choice",
            type=StepType.CHOICE,
            content="Choose",
            options=[{"text": "opt1", "value": "Yes"}],
            next_step="next"
        )

        mock_definition = Mock(spec=WorkflowDefinition)
        variables = {}  # No choice made yet

        with patch('app.services.execution.workflow_executor.WorkflowParser') as mock_parser:
            def get_step_side_effect(definition, step_id):
                step_map = {
                    "cond1": condition_step,
                    "choice1": choice_step
                }
                return step_map.get(step_id)

            mock_parser.get_step_by_id.side_effect = get_step_side_effect

            with patch.object(executor, 'execute_step') as mock_execute:
                async def execute_side_effect(execution, step, definition, variables):
                    if step.id == "cond1":
                        return StepExecutionResult(
                            success=True,
                            step_id="cond1",
                            step_type=StepType.CONDITION,
                            next_step_id="choice1",
                            workflow_completed=False,
                            input_required=None,
                            workflow_id="test-workflow"
                        )
                    else:  # choice1 - waiting for input
                        return StepExecutionResult(
                            success=True,
                            step_id="choice1",
                            step_type=StepType.CHOICE,
                            next_step_id=None,
                            workflow_completed=False,
                            input_required="choice",  # NEEDS INPUT!
                            workflow_id="test-workflow"
                        )

                mock_execute.side_effect = execute_side_effect

                # Execute
                result = await executor.auto_execute_steps(
                    execution=mock_execution,
                    start_step_id="cond1",
                    definition=mock_definition,
                    variables=variables,
                    max_steps=50
                )

                # Should stop at choice and wait for input
                assert result.input_required == "choice"
                assert result.step_id == "choice1"
                assert mock_execution.steps_completed == 2  # CONDITION + CHOICE
                assert mock_execution.status == ExecutionStatus.RUNNING.value  # Still running

    @pytest.mark.asyncio
    async def test_auto_execution_prevents_infinite_loops(
        self, executor, mock_execution, mock_db
    ):
        """
        Verify auto-execution stops at max_steps to prevent infinite loops.
        """
        # Create circular workflow (should never happen, but safety check)
        step1 = WorkflowStep(
            id="step1",
            name="Loop",
            type=StepType.CONDITION,
            condition="true",
            true_step="step2",
            false_step=None
        )
        step2 = WorkflowStep(
            id="step2",
            name="Loop back",
            type=StepType.CONDITION,
            condition="true",
            true_step="step1",  # Loop!
            false_step=None
        )

        mock_definition = Mock(spec=WorkflowDefinition)
        variables = {}

        with patch('app.services.execution.workflow_executor.WorkflowParser') as mock_parser:
            def get_step_side_effect(definition, step_id):
                return step1 if step_id == "step1" else step2

            mock_parser.get_step_by_id.side_effect = get_step_side_effect

            with patch.object(executor, 'execute_step') as mock_execute:
                async def execute_side_effect(execution, step, definition, variables):
                    next_step = "step2" if step.id == "step1" else "step1"
                    return StepExecutionResult(
                        success=True,
                        step_id=step.id,
                        step_type=StepType.CONDITION,
                        next_step_id=next_step,
                        workflow_completed=False,
                        input_required=None,
                        workflow_id="test-workflow"
                    )

                mock_execute.side_effect = execute_side_effect

                # Execute with low max_steps
                result = await executor.auto_execute_steps(
                    execution=mock_execution,
                    start_step_id="step1",
                    definition=mock_definition,
                    variables=variables,
                    max_steps=10  # Should stop here
                )

                # Should stop at max_steps
                assert mock_execution.steps_completed == 10
                assert mock_execution.status == ExecutionStatus.FAILED.value
                assert "infinite loop" in mock_execution.error_message.lower()
                assert result.success is False

    @pytest.mark.asyncio
    async def test_workflow_completes_at_final_step(
        self, executor, mock_execution, mock_db
    ):
        """Verify workflow properly completes when reaching final step"""
        final_step = WorkflowStep(
            id="final",
            name="Final Action",
            type=StepType.ACTION,
            action="send_email",
            params={},
            next_step=None  # No next step
        )

        mock_definition = Mock(spec=WorkflowDefinition)
        variables = {}

        with patch('app.services.execution.workflow_executor.WorkflowParser') as mock_parser:
            mock_parser.get_step_by_id.return_value = final_step

            with patch.object(executor, 'execute_step') as mock_execute:
                async def execute_side_effect(execution, step, definition, variables):
                    return StepExecutionResult(
                        success=True,
                        step_id="final",
                        step_type=StepType.ACTION,
                        next_step_id=None,
                        workflow_completed=True,  # Workflow completes
                        input_required=None,
                        workflow_id="test-workflow"
                    )

                mock_execute.side_effect = execute_side_effect

                result = await executor.auto_execute_steps(
                    execution=mock_execution,
                    start_step_id="final",
                    definition=mock_definition,
                    variables=variables,
                    max_steps=50
                )

                # Should mark execution as completed
                assert result.workflow_completed is True
                assert mock_execution.status == ExecutionStatus.COMPLETED.value
                assert mock_execution.completed_at is not None
                assert mock_execution.steps_completed == 1
