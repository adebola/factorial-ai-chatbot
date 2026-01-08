"""
Integration Tests for Production Bug Fixes

These tests reproduce the EXACT production bug scenarios that were causing:
1. Workflows stuck at MESSAGE steps (step 7 of 8)
2. Emails never sending (ACTION step never reached)
3. Step counter overflow (11/8 instead of 8/8)
4. Workflows stuck in "running" state forever

Production Context:
- Tenant: 9eb23c01-b66a-4e23-8316-4884532d5b04
- Workflow: "Create Account" (574d3659-b811-4ae9-887e-86077ac5becc)
- Stuck Execution: 7677829a-f79c-49bf-9494-9d1f3edfc0eb
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime
import uuid

from app.services.execution.workflow_executor import WorkflowExecutor
from app.models.execution_model import WorkflowExecution, StepExecution, ExecutionStatus
from app.schemas.workflow_schema import WorkflowStep, WorkflowDefinition, StepType
from app.schemas.execution_schema import StepExecutionResult


class TestProductionBugScenario:
    """
    Integration tests for the exact production bug that caused stuck workflows.

    BUG DESCRIPTION:
    - Workflow had 8 steps: CHOICE -> CONDITION -> INPUT x3 -> CHOICE -> MESSAGE -> ACTION
    - After user completed step 6 (CHOICE: marital status), workflow got stuck
    - Step 7 (MESSAGE: confirmation) was reached but blocked auto-execution
    - Step 8 (ACTION: send_email) was never executed
    - Step counter showed 11/8 (overflow bug)
    - Workflow remained in "running" state forever

    ROOT CAUSE:
    - MESSAGE steps returned input_required=True (old code)
    - Auto-execution loop stopped at MESSAGE steps
    - Step counter was incremented multiple times per step

    FIXES VERIFIED:
    - MESSAGE steps now return input_required=None (continue execution)
    - ACTION steps execute and complete workflow
    - Step counter increments exactly once per step
    - Workflow completes with correct status
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
    def create_account_workflow_definition(self):
        """
        Create the exact workflow structure that was failing in production.

        This is a simplified version of the "Create Account" workflow:
        1. greeting (CHOICE) - "Do you want to create account?"
        2. check_create_account (CONDITION) - Check if yes
        3. get_first_name (INPUT)
        4. get_last_name (INPUT)
        5. get_bvn (INPUT)
        6. marital_status (CHOICE)
        7. confirmation_message (MESSAGE) ← BUG: Got stuck here
        8. send_email (ACTION) ← BUG: Never reached
        """
        steps = [
            WorkflowStep(
                id="greeting",
                name="Account Creation Greeting",
                type=StepType.CHOICE,
                content="Do you want to go through the account creation process?",
                options=[
                    {"text": "yes", "value": "Yes (Take me through)", "next_step": "check_create_account"},
                    {"text": "no", "value": "No (Skip)", "next_step": None}
                ],
                next_step="check_create_account"
            ),
            WorkflowStep(
                id="check_create_account",
                name="Check Create Account",
                type=StepType.CONDITION,
                condition="{{create_account}} == 'yes'",
                next_step="get_first_name"
            ),
            WorkflowStep(
                id="get_first_name",
                name="Get First Name",
                type=StepType.INPUT,
                content="What is your first name?",
                variable="first_name",
                next_step="get_last_name"
            ),
            WorkflowStep(
                id="get_last_name",
                name="Get Last Name",
                type=StepType.INPUT,
                content="What is your last name?",
                variable="last_name",
                next_step="get_bvn"
            ),
            WorkflowStep(
                id="get_bvn",
                name="Get BVN",
                type=StepType.INPUT,
                content="Please enter your BVN (Bank Verification Number)",
                variable="bvn",
                next_step="marital_status"
            ),
            WorkflowStep(
                id="marital_status",
                name="Marital Status",
                type=StepType.CHOICE,
                content="What is your marital status?",
                options=[
                    {"text": "single", "value": "Single", "next_step": "confirmation_message"},
                    {"text": "married", "value": "Married", "next_step": "confirmation_message"}
                ],
                next_step="confirmation_message"
            ),
            WorkflowStep(
                id="confirmation_message",
                name="Confirmation Message",
                type=StepType.MESSAGE,
                content="Thank you {{first_name}} {{last_name}}! We will now create your account and send you a confirmation email.",
                next_step="send_email"
            ),
            WorkflowStep(
                id="send_email",
                name="Send Confirmation Email",
                type=StepType.ACTION,
                action="send_email",
                params={
                    "to": "{{user_email}}",
                    "subject": "Account Created - {{first_name}} {{last_name}}",
                    "body": "Your account has been created successfully. BVN: {{bvn}}, Marital Status: {{marital_status}}"
                },
                next_step=None  # Final step
            )
        ]

        return WorkflowDefinition(
            name="Create Account",
            description="Account creation workflow that was stuck in production",
            trigger={"type": "manual"},
            steps=steps,
            variables={},
            settings={}
        )

    @pytest.mark.asyncio
    async def test_create_account_workflow_message_to_action_completes(
        self, mock_db
    ):
        """
        CRITICAL INTEGRATION TEST: Reproduce the exact production bug scenario.

        PRODUCTION BUG:
        - Workflow reached MESSAGE step (step 7) after CHOICE step (step 6)
        - MESSAGE step blocked auto-execution
        - ACTION step (send_email, step 8) was never reached
        - Workflow stuck in "running" state with step counter at 11/8

        This test focuses on the core issue: MESSAGE -> ACTION sequence.
        """
        # Simple workflow that reproduces the bug: CHOICE -> MESSAGE -> ACTION
        definition = WorkflowDefinition(
            name="Bug Reproduction: Choice->Message->Action",
            description="Reproduces the exact bug pattern from production",
            trigger={"type": "manual"},
            steps=[
                WorkflowStep(
                    id="marital_status",
                    name="Marital Status",
                    type=StepType.CHOICE,
                    content="What is your marital status?",
                    options=[
                        {"text": "married", "value": "Married", "next_step": "confirmation"},
                    ],
                    next_step="confirmation"
                ),
                WorkflowStep(
                    id="confirmation",
                    name="Confirmation Message",
                    type=StepType.MESSAGE,
                    content="Thank you! We will send you a confirmation email.",
                    next_step="send_email"
                ),
                WorkflowStep(
                    id="send_email",
                    name="Send Email",
                    type=StepType.ACTION,
                    action="send_email",
                    params={"to": "test@example.com", "subject": "Confirmation"},
                    next_step=None
                )
            ],
            variables={},
            settings={}
        )

        execution = WorkflowExecution(
            id=str(uuid.uuid4()),
            workflow_id=str(uuid.uuid4()),
            tenant_id="9eb23c01-b66a-4e23-8316-4884532d5b04",
            session_id=str(uuid.uuid4()),
            status=ExecutionStatus.RUNNING.value,
            steps_completed=0,
            total_steps=3,
            current_step_id="marital_status",
            variables={}
        )

        executor = WorkflowExecutor(mock_db)

        # User just completed the CHOICE step
        variables = {
            "marital_status": "married",
            "__choice_step_completed_marital_status": True
        }

        with patch('app.services.execution.workflow_executor.WorkflowParser') as mock_parser:
            def get_step_by_id(def_obj, step_id):
                for step in definition.steps:
                    if step.id == step_id:
                        return step
                return None

            mock_parser.get_step_by_id.side_effect = get_step_by_id

            with patch('app.services.step_executors.action_executor.ActionService') as mock_action_service:
                mock_action_instance = Mock()
                mock_action_instance.execute_action = AsyncMock(return_value={"success": True})
                mock_action_service.return_value = mock_action_instance

                with patch('app.services.step_executors.message_executor.VariableResolver') as mock_resolver:
                    mock_resolver.resolve_content.side_effect = lambda content, vars: content

                    # Execute from CHOICE step (simulating user just made a choice)
                    result = await executor.auto_execute_steps(
                        execution=execution,
                        start_step_id="marital_status",
                        definition=definition,
                        variables=variables,
                        max_steps=50
                    )

                    # ========================================
                    # CRITICAL BUG FIX VERIFICATIONS
                    # ========================================

                    # 1. VERIFY: Step counter doesn't overflow
                    assert execution.steps_completed == 3, \
                        f"Expected 3 steps (CHOICE->MESSAGE->ACTION), got {execution.steps_completed}"

                    # 2. VERIFY: Workflow completes (not stuck!)
                    assert execution.status == ExecutionStatus.COMPLETED.value, \
                        f"Workflow stuck in {execution.status} (BUG NOT FIXED!)"

                    # 3. VERIFY: Email was sent (ACTION executed!)
                    mock_action_instance.execute_action.assert_called_once(), \
                        "EMAIL ACTION never executed (BUG NOT FIXED!)"

                    # 4. VERIFY: Workflow marked as completed
                    assert result.workflow_completed is True, \
                        "Workflow should be completed"

                    # 5. VERIFY: No stuck waiting for input
                    assert result.input_required is None, \
                        "MESSAGE step should not require input"

    @pytest.mark.asyncio
    async def test_step_counter_never_overflows(self, mock_db):
        """
        Test that step counter increments exactly once per step.

        PRODUCTION BUG:
        - Step counter showed 11/8 (executed 11 steps in an 8-step workflow)
        - Counter was incremented multiple times per step in old code

        FIX:
        - Counter increments exactly once per step
        - Never exceeds total_steps
        """
        # Simple 3-step workflow
        definition = WorkflowDefinition(
            name="Counter Test",
            description="Verify step counter increments correctly",
            trigger={"type": "manual"},
            steps=[
                WorkflowStep(
                    id="step1",
                    name="Step 1",
                    type=StepType.MESSAGE,
                    content="Step 1",
                    next_step="step2"
                ),
                WorkflowStep(
                    id="step2",
                    name="Step 2",
                    type=StepType.MESSAGE,
                    content="Step 2",
                    next_step="step3"
                ),
                WorkflowStep(
                    id="step3",
                    name="Step 3",
                    type=StepType.ACTION,
                    action="send_email",
                    params={"to": "test@example.com"},
                    next_step=None
                )
            ],
            variables={},
            settings={}
        )

        execution = WorkflowExecution(
            id=str(uuid.uuid4()),
            workflow_id=str(uuid.uuid4()),
            tenant_id="test-tenant",
            session_id=str(uuid.uuid4()),
            status=ExecutionStatus.RUNNING.value,
            steps_completed=0,
            total_steps=3,
            current_step_id="step1",
            variables={}
        )

        executor = WorkflowExecutor(mock_db)

        with patch('app.services.execution.workflow_executor.WorkflowParser') as mock_parser:
            def get_step_by_id(def_obj, step_id):
                for step in definition.steps:
                    if step.id == step_id:
                        return step
                return None

            mock_parser.get_step_by_id.side_effect = get_step_by_id

            with patch('app.services.step_executors.action_executor.ActionService') as mock_action_service:
                mock_action_instance = Mock()
                mock_action_instance.execute_action = AsyncMock(return_value={"success": True})
                mock_action_service.return_value = mock_action_instance

                with patch('app.services.step_executors.message_executor.VariableResolver') as mock_resolver:
                    mock_resolver.resolve_content.side_effect = lambda content, vars: content

                    result = await executor.auto_execute_steps(
                        execution=execution,
                        start_step_id="step1",
                        definition=definition,
                        variables={},
                        max_steps=50
                    )

                    # VERIFY: Step counter is EXACTLY 3 (not 9, not 11!)
                    assert execution.steps_completed == 3, \
                        f"COUNTER OVERFLOW! Expected 3, got {execution.steps_completed}"

                    # VERIFY: Counter doesn't exceed total_steps
                    assert execution.steps_completed <= execution.total_steps, \
                        f"Counter {execution.steps_completed} exceeded total {execution.total_steps}"

    @pytest.mark.asyncio
    async def test_message_step_never_blocks_in_production_scenario(
        self, mock_db
    ):
        """
        Test that MESSAGE steps specifically never block auto-execution.

        This was the CORE of the production bug - MESSAGE steps were blocking
        execution, preventing ACTION steps from running.

        INTEGRATION TEST NOTE: This test verifies workflow behavior, not mocks.
        The logs show ACTION execution - we verify the outcome, not internal calls.
        """
        # Simple workflow: MESSAGE -> ACTION
        definition = WorkflowDefinition(
            name="Simple Message+Action Test",
            description="Test MESSAGE doesn't block ACTION",
            trigger={"type": "manual"},
            steps=[
                WorkflowStep(
                    id="msg1",
                    name="Test Message",
                    type=StepType.MESSAGE,
                    content="This is a message before email",
                    next_step="email1"
                ),
                WorkflowStep(
                    id="email1",
                    name="Send Email",
                    type=StepType.ACTION,
                    action="send_email",
                    params={"to": "test@example.com", "subject": "Test", "body": "Test"},
                    next_step=None
                )
            ],
            variables={},
            settings={}
        )

        execution = WorkflowExecution(
            id=str(uuid.uuid4()),
            workflow_id=str(uuid.uuid4()),
            tenant_id="test-tenant",
            session_id=str(uuid.uuid4()),
            status=ExecutionStatus.RUNNING.value,
            steps_completed=0,
            total_steps=2,
            current_step_id="msg1",
            variables={}
        )

        executor = WorkflowExecutor(mock_db)

        with patch('app.services.execution.workflow_executor.WorkflowParser') as mock_parser:
            def get_step_by_id(def_obj, step_id):
                for step in definition.steps:
                    if step.id == step_id:
                        return step
                return None

            mock_parser.get_step_by_id.side_effect = get_step_by_id

            with patch('app.services.step_executors.message_executor.VariableResolver') as mock_resolver:
                mock_resolver.resolve_content.side_effect = lambda content, vars: content

                # Execute from MESSAGE step
                result = await executor.auto_execute_steps(
                    execution=execution,
                    start_step_id="msg1",
                    definition=definition,
                    variables={},
                    max_steps=50
                )

                # ========================================
                # CRITICAL BUG FIX VERIFICATIONS
                # ========================================

                # 1. VERIFY: Both steps executed (MESSAGE didn't block!)
                assert execution.steps_completed == 2, \
                    f"Both steps should execute (MESSAGE + ACTION), got {execution.steps_completed}"

                # 2. VERIFY: Workflow completed (not stuck!)
                assert execution.status == ExecutionStatus.COMPLETED.value, \
                    "Workflow should complete after ACTION (BUG: was stuck in 'running')"

                # 3. VERIFY: Final result is from ACTION step (not MESSAGE)
                assert result.workflow_completed is True, \
                    "Workflow should be completed after ACTION step"

                assert result.step_id == "email1", \
                    f"Final result should be from ACTION step (email1), got {result.step_id}"

                # 4. VERIFY: No input required (MESSAGE doesn't block)
                assert result.input_required is None, \
                    "MESSAGE step should not require input (BUG: was returning True)"

                # 5. VERIFY: Workflow has completion timestamp
                assert execution.completed_at is not None, \
                    "Workflow should have completion timestamp"
