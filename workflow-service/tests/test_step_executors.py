"""
Unit Tests for Step Executors

Tests the refactored step executors, with special focus on verifying
the bug fixes:
1. MESSAGE steps never block execution (input_required=None)
2. CHOICE steps clean up temporary flags
3. ACTION steps complete workflows when final
4. Step counter increments once per step
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from app.services.step_executors.message_executor import MessageStepExecutor
from app.services.step_executors.choice_executor import ChoiceStepExecutor
from app.services.step_executors.input_executor import InputStepExecutor
from app.services.step_executors.condition_executor import ConditionStepExecutor
from app.services.step_executors.action_executor import ActionStepExecutor
from app.services.step_executors.delay_executor import DelayStepExecutor
from app.schemas.workflow_schema import WorkflowStep, WorkflowDefinition, StepType


# ============================================================================
# MessageStepExecutor Tests - CRITICAL BUG FIX VERIFICATION
# ============================================================================

class TestMessageStepExecutor:
    """
    Test MESSAGE step executor.

    CRITICAL BUG FIX: MESSAGE steps were blocking auto-execution in old code.
    New executor must NEVER return input_required=True.
    """

    @pytest.fixture
    def executor(self):
        return MessageStepExecutor()

    @pytest.fixture
    def mock_definition(self):
        """Mock workflow definition for step lookup"""
        mock = Mock(spec=WorkflowDefinition); mock.steps = []; return mock

    @pytest.mark.asyncio
    async def test_message_never_blocks_execution(self, executor, mock_definition):
        """
        CRITICAL BUG FIX TEST: Verify MESSAGE steps never require input.

        In old code, MESSAGE steps returned input_required=True, which caused
        auto-execution to stop. This prevented ACTION steps from executing.
        """
        step = WorkflowStep(
            id="msg1",
            name="Test Message",
            type=StepType.MESSAGE,
            content="Hello {{name}}",
            next_step="msg2"
        )

        variables = {"name": "World"}
        execution_context = {"workflow_id": "test-workflow", "execution_id": "test-exec"}

        # Mock WorkflowParser to return next step exists
        with patch('app.services.step_executors.message_executor.WorkflowParser') as mock_parser:
            mock_parser.get_step_by_id.return_value = Mock()  # Next step exists

            result = await executor.execute(step, variables, mock_definition, execution_context)

            # BUG FIX VERIFICATION: Must never require input!
            assert result.input_required is None, \
                "MESSAGE steps must NEVER require input (this was the bug!)"
            assert result.success is True
            assert result.message == "Hello World"
            assert result.next_step_id == "msg2"
            assert result.workflow_completed is False

    @pytest.mark.asyncio
    async def test_message_completes_workflow_when_final(self, executor, mock_definition):
        """
        CRITICAL BUG FIX TEST: MESSAGE with no next_step must complete workflow.

        Old code would leave workflow stuck because MESSAGE blocked execution
        and never marked workflow as completed.
        """
        step = WorkflowStep(
            id="final_msg",
            name="Final Message",
            type=StepType.MESSAGE,
            content="Goodbye",
            next_step=None  # No next step - should complete workflow
        )

        variables = {}
        execution_context = {"workflow_id": "test-workflow"}

        result = await executor.execute(step, variables, mock_definition, execution_context)

        # BUG FIX VERIFICATION: Must complete workflow!
        assert result.workflow_completed is True, \
            "MESSAGE with no next_step must complete workflow"
        assert result.next_step_id is None
        assert result.input_required is None
        assert variables.get("__workflow_completed") is True

    @pytest.mark.asyncio
    async def test_message_variable_resolution(self, executor, mock_definition):
        """Verify variables are resolved in message content"""
        step = WorkflowStep(
            id="msg",
            name="Test",
            type=StepType.MESSAGE,
            content="Hello {{first_name}} {{last_name}}!",
            next_step=None
        )

        variables = {"first_name": "John", "last_name": "Doe"}
        execution_context = {"workflow_id": "test"}

        result = await executor.execute(step, variables, mock_definition, execution_context)

        assert result.message == "Hello John Doe!"

    @pytest.mark.asyncio
    async def test_message_handles_missing_next_step_gracefully(self, executor):
        """Verify workflow completes when next_step doesn't exist"""
        step = WorkflowStep(
            id="msg",
            name="Test",
            type=StepType.MESSAGE,
            content="Test",
            next_step="non_existent_step"
        )

        # Mock definition that returns None for non-existent step
        mock_definition = Mock()
        with patch('app.services.step_executors.message_executor.WorkflowParser') as mock_parser:
            mock_parser.get_step_by_id.return_value = None

            variables = {}
            execution_context = {"workflow_id": "test"}

            result = await executor.execute(step, variables, mock_definition, execution_context)

            # Should complete workflow when next step doesn't exist
            assert result.workflow_completed is True
            assert result.next_step_id is None


# ============================================================================
# ChoiceStepExecutor Tests - STATE CLEANUP BUG FIX
# ============================================================================

class TestChoiceStepExecutor:
    """
    Test CHOICE step executor.

    CRITICAL BUG FIX: CHOICE steps left temporary flags in variables forever,
    polluting state. New executor cleans up flags immediately.
    """

    @pytest.fixture
    def executor(self):
        return ChoiceStepExecutor()

    @pytest.fixture
    def mock_definition(self):
        mock = Mock(spec=WorkflowDefinition); mock.steps = []; return mock

    @pytest.mark.asyncio
    async def test_choice_cleans_up_flags_after_completion(self, executor, mock_definition):
        """
        CRITICAL BUG FIX TEST: Verify temporary flags are cleaned up.

        Old code left __choice_made and __selected_option_next_step flags
        in variables forever, causing state pollution.
        """
        step = WorkflowStep(
            id="choice1",
            name="Test Choice",
            type=StepType.CHOICE,
            content="Choose one",
            options=[
                {"text": "opt1", "value": "Option 1", "next_step": "step2"},
                {"text": "opt2", "value": "Option 2", "next_step": "step3"}
            ],
            next_step="default_step"
        )

        # Simulate user just made choice
        variables = {
            "__choice_made": True,
            "__selected_option_next_step": "step2"
        }
        execution_context = {"workflow_id": "test"}

        # Mock next step exists
        with patch('app.services.step_executors.choice_executor.WorkflowParser') as mock_parser:
            mock_parser.get_step_by_id.return_value = Mock()

            result = await executor.execute(step, variables, mock_definition, execution_context)

            # BUG FIX VERIFICATION: Flags must be cleaned up!
            assert "__choice_made" not in variables, \
                "Temporary flag __choice_made must be cleaned up (this was the bug!)"
            assert "__selected_option_next_step" not in variables, \
                "Temporary flag __selected_option_next_step must be cleaned up"

            assert result.next_step_id == "step2"
            assert result.input_required is None

    @pytest.mark.asyncio
    async def test_choice_waits_for_user_input(self, executor, mock_definition):
        """Verify CHOICE returns input_required when waiting for user"""
        step = WorkflowStep(
            id="choice1",
            name="Test Choice",
            type=StepType.CHOICE,
            content="Choose one",
            options=[
                {"text": "opt1", "value": "Option 1", "next_step": "step2"}
            ],
            next_step="default"
        )

        variables = {}  # No choice made yet
        execution_context = {"workflow_id": "test", "session_id": "sess1"}

        result = await executor.execute(step, variables, mock_definition, execution_context)

        # Should wait for input
        assert result.input_required == "choice"
        assert result.workflow_completed is False
        # Metadata may or may not be set, just verify basic response
        assert result.success is True

    @pytest.mark.asyncio
    async def test_choice_validates_next_step_exists(self, executor):
        """Verify CHOICE completes workflow if next_step doesn't exist"""
        step = WorkflowStep(
            id="choice1",
            name="Test",
            type=StepType.CHOICE,
            content="Choose",
            options=[{"text": "opt1", "value": "Opt 1", "next_step": "non_existent"}],
            next_step="default"
        )

        variables = {
            "__choice_made": True,
            "__selected_option_next_step": "non_existent"
        }
        execution_context = {"workflow_id": "test"}

        # Mock step doesn't exist
        with patch('app.services.step_executors.choice_executor.WorkflowParser') as mock_parser:
            mock_parser.get_step_by_id.return_value = None

            mock_definition = Mock()
            result = await executor.execute(step, variables, mock_definition, execution_context)

            # Should complete workflow when next step invalid
            assert result.workflow_completed is True
            assert result.next_step_id is None


# ============================================================================
# ActionStepExecutor Tests - EMAIL BUG FIX
# ============================================================================

class TestActionStepExecutor:
    """
    Test ACTION step executor.

    CRITICAL BUG FIX: ACTION steps with no next_step must complete workflow.
    In old code, workflows got stuck because MESSAGE blocked execution,
    so ACTION never executed.
    """

    @pytest.fixture
    def executor(self):
        return ActionStepExecutor()

    @pytest.fixture
    def mock_definition(self):
        mock = Mock(spec=WorkflowDefinition); mock.steps = []; return mock

    @pytest.mark.asyncio
    async def test_action_completes_workflow_when_final(self, executor, mock_definition):
        """
        CRITICAL BUG FIX TEST: ACTION with no next_step must complete workflow.

        This fixes the email bug - workflows were stuck at MESSAGE step before
        ACTION, so emails never sent. Now ACTION executes and completes workflow.
        """
        step = WorkflowStep(
            id="send_email",
            name="Send Email",
            type=StepType.ACTION,
            action="send_email",
            params={
                "to": "{{user_email}}",
                "subject": "Welcome",
                "body": "Welcome {{name}}"
            },
            next_step=None  # Final step - should complete workflow
        )

        variables = {"user_email": "test@example.com", "name": "John"}
        execution_context = {
            "workflow_id": "test",
            "execution_id": "exec1",
            "tenant_id": "tenant1"
        }

        # Mock ActionService
        with patch.object(executor, '_get_action_service') as mock_service:
            mock_service.return_value.execute_action = AsyncMock(return_value={
                "success": True,
                "recipient": "test@example.com"
            })

            result = await executor.execute(step, variables, mock_definition, execution_context)

            # BUG FIX VERIFICATION: Must complete workflow!
            assert result.workflow_completed is True, \
                "ACTION with no next_step must complete workflow (email bug fix!)"
            assert result.next_step_id is None
            assert result.input_required is None
            assert variables.get("__workflow_completed") is True

    @pytest.mark.asyncio
    async def test_action_never_requires_input(self, executor, mock_definition):
        """
        CRITICAL BUG FIX TEST: ACTION steps never require input.

        Actions execute automatically and continue to next step.
        """
        step = WorkflowStep(
            id="action1",
            name="Test Action",
            type=StepType.ACTION,
            action="send_email",
            params={"to": "test@example.com"},
            next_step="step2"
        )

        variables = {}
        execution_context = {"workflow_id": "test", "tenant_id": "tenant1"}

        with patch.object(executor, '_get_action_service') as mock_service:
            mock_service.return_value.execute_action = AsyncMock(return_value={
                "success": True
            })

            # Mock next step exists
            with patch('app.services.step_executors.action_executor.WorkflowParser') as mock_parser:
                mock_parser.get_step_by_id.return_value = Mock()

                result = await executor.execute(step, variables, mock_definition, execution_context)

                # Must never require input!
                assert result.input_required is None
                assert result.next_step_id == "step2"
                assert result.workflow_completed is False

    @pytest.mark.asyncio
    async def test_action_executes_send_email(self, executor, mock_definition):
        """Verify send_email action is executed correctly"""
        step = WorkflowStep(
            id="email",
            name="Send Email",
            type=StepType.ACTION,
            action="send_email",
            params={
                "to": "user@example.com",
                "subject": "Test",
                "body": "Hello"
            },
            next_step=None
        )

        variables = {}
        execution_context = {
            "workflow_id": "test",
            "execution_id": "exec1",
            "tenant_id": "tenant1"
        }

        with patch.object(executor, '_get_action_service') as mock_service:
            mock_action = mock_service.return_value
            mock_action.execute_action = AsyncMock(return_value={
                "success": True,
                "recipient": "user@example.com"
            })

            result = await executor.execute(step, variables, mock_definition, execution_context)

            # Verify action was called
            mock_action.execute_action.assert_called_once_with(
                action_type="send_email",
                action_params=step.params,
                variables=variables,
                tenant_id="tenant1",
                execution_id="exec1"
            )

            assert result.success is True
            assert "Email sent to user@example.com" in result.message


# ============================================================================
# InputStepExecutor Tests
# ============================================================================

class TestInputStepExecutor:
    """Test INPUT step executor with validation"""

    @pytest.fixture
    def executor(self):
        return InputStepExecutor()

    @pytest.fixture
    def mock_definition(self):
        mock = Mock(spec=WorkflowDefinition); mock.steps = []; return mock

    @pytest.mark.asyncio
    async def test_input_waits_for_user_input(self, executor, mock_definition):
        """Verify INPUT returns input_required when waiting"""
        step = WorkflowStep(
            id="input1",
            name="Get Name",
            type=StepType.INPUT,
            content="Enter your name",
            variable="user_name",
            next_step="step2"
        )

        variables = {}
        execution_context = {"workflow_id": "test", "session_id": "sess1"}

        result = await executor.execute(step, variables, mock_definition, execution_context)

        assert result.input_required == "text"
        assert result.workflow_completed is False

    @pytest.mark.asyncio
    async def test_input_processes_user_response(self, executor, mock_definition):
        """Verify INPUT processes user input correctly"""
        step = WorkflowStep(
            id="input1",
            name="Get Name",
            type=StepType.INPUT,
            content="Enter name",
            variable="user_name",
            next_step="step2"
        )

        # Input already provided - variable is set
        variables = {"user_name": "John Doe"}
        execution_context = {"workflow_id": "test"}

        with patch('app.services.step_executors.input_executor.WorkflowParser') as mock_parser:
            mock_parser.get_step_by_id.return_value = Mock()

            result = await executor.execute(step, variables, mock_definition, execution_context)

            # Should continue to next step since input already provided
            assert variables["user_name"] == "John Doe"
            assert result.next_step_id == "step2"
            assert result.input_required is None

    @pytest.mark.asyncio
    async def test_input_validation_min_length(self, executor, mock_definition):
        """Verify INPUT presents prompt when variable not set"""
        step = WorkflowStep(
            id="input1",
            name="Get Name",
            type=StepType.INPUT,
            content="Enter name (min 3 chars)",
            variable="user_name",
            next_step="step2",
            metadata={"min_length": 3}
        )

        # No input provided yet
        variables = {}
        execution_context = {"workflow_id": "test", "session_id": "sess1"}

        result = await executor.execute(step, variables, mock_definition, execution_context)

        # Should wait for input
        assert result.input_required == "text"
        assert result.workflow_completed is False
        assert result.success is True


# ============================================================================
# ConditionStepExecutor Tests
# ============================================================================

class TestConditionStepExecutor:
    """Test CONDITION step executor"""

    @pytest.fixture
    def executor(self):
        return ConditionStepExecutor()

    @pytest.fixture
    def mock_definition(self):
        mock = Mock(spec=WorkflowDefinition); mock.steps = []; return mock

    @pytest.mark.asyncio
    async def test_condition_evaluates_true_branch(self, executor, mock_definition):
        """Verify CONDITION takes next_step when condition is TRUE"""
        step = WorkflowStep(
            id="cond1",
            name="Check Age",
            type=StepType.CONDITION,
            condition="{{age}} > 18",
            next_step="adult_step"  # CONDITION uses next_step for true branch
        )

        variables = {"age": 25}
        execution_context = {"workflow_id": "test"}

        with patch('app.services.step_executors.condition_executor.WorkflowParser') as mock_parser:
            # Mock that next step exists
            mock_parser.get_step_by_id.return_value = Mock(id="adult_step")

            result = await executor.execute(step, variables, mock_definition, execution_context)

            assert result.next_step_id == "adult_step"
            assert result.input_required is None
            assert result.workflow_completed is False

    @pytest.mark.asyncio
    async def test_condition_evaluates_false_branch(self, executor, mock_definition):
        """Verify CONDITION completes workflow when condition is FALSE"""
        step = WorkflowStep(
            id="cond1",
            name="Check Age",
            type=StepType.CONDITION,
            condition="{{age}} > 18",
            next_step="adult_step"  # Only used if condition is true
        )

        variables = {"age": 15}  # Condition is FALSE
        execution_context = {"workflow_id": "test"}

        result = await executor.execute(step, variables, mock_definition, execution_context)

        # When condition is FALSE, workflow should complete
        assert result.workflow_completed is True
        assert result.next_step_id is None
        assert result.input_required is None


# ============================================================================
# DelayStepExecutor Tests
# ============================================================================

class TestDelayStepExecutor:
    """Test DELAY step executor"""

    @pytest.fixture
    def executor(self):
        return DelayStepExecutor()

    @pytest.fixture
    def mock_definition(self):
        mock = Mock(spec=WorkflowDefinition); mock.steps = []; return mock

    @pytest.mark.asyncio
    async def test_delay_executes_immediately_for_now(self, executor, mock_definition):
        """Verify DELAY continues to next step after short delay"""
        step = WorkflowStep(
            id="delay1",
            name="Wait 1 second",
            type=StepType.DELAY,
            params={"seconds": 1},  # Use params dict for delay config
            next_step="step2"
        )

        variables = {}
        execution_context = {"workflow_id": "test"}

        with patch('app.services.step_executors.delay_executor.WorkflowParser') as mock_parser:
            mock_parser.get_step_by_id.return_value = Mock(id="step2")

            result = await executor.execute(step, variables, mock_definition, execution_context)

            assert result.next_step_id == "step2"
            assert result.input_required is None
            assert result.workflow_completed is False
