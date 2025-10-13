"""
Execution service for running workflows.
Handles the complete lifecycle of workflow execution.
"""
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime
from sqlalchemy.orm import Session

from ..models.workflow_model import Workflow
from ..models.execution_model import (
    WorkflowExecution, StepExecution, ExecutionStatus, StepType
)
from ..schemas.execution_schema import (
    ExecutionStartRequest, ExecutionStepRequest, StepExecutionResult,
    WorkflowExecutionResponse, ExecutionSummary, ExecutionList
)
from ..schemas.workflow_schema import StepType as SchemaStepType
from ..core.exceptions import (
    WorkflowExecutionError, StepExecutionError, WorkflowNotFoundError, WorkflowStateError
)
from ..core.logging_config import get_logger
from .workflow_parser import WorkflowParser
from .variable_resolver import VariableResolver
from .action_service import ActionService
from .state_manager import StateManager

logger = get_logger("execution_service")


class ExecutionService:
    """Service for executing workflows"""

    def __init__(self, db: Session):
        self.db = db
        self.action_service = ActionService(db=db)
        self.state_manager = StateManager(db)

    async def start_execution(
        self,
        request: ExecutionStartRequest,
        tenant_id: str,
        user_identifier: Optional[str] = None
    ) -> WorkflowExecutionResponse:
        """
        Start a new workflow execution.

        Args:
            request: Execution start request
            tenant_id: Tenant ID
            user_identifier: Optional user identifier

        Returns:
            Workflow execution response
        """
        try:
            # Get the workflow
            workflow = self.db.query(Workflow).filter(
                Workflow.id == request.workflow_id,
                Workflow.tenant_id == tenant_id
            ).first()

            if not workflow:
                logger.error(f"Workflow {request.workflow_id} not found")
                raise WorkflowNotFoundError(f"Workflow {request.workflow_id} not found")

            if not workflow.is_active:
                logger.error("Cannot execute inactive workflow")
                raise WorkflowExecutionError("Cannot execute inactive workflow")

            # Parse workflow definition
            definition = WorkflowParser.parse_from_dict(workflow.definition)

            # Get the first step
            first_step = WorkflowParser.get_first_step(definition)
            if not first_step:
                raise WorkflowExecutionError("Workflow has no steps")

            # Initialize variables
            variables = VariableResolver.merge_variables(
                definition.variables or {},
                request.initial_variables or {},
                request.context or {}
            )
            variables = VariableResolver.add_system_variables(variables)

            # Create an execution record
            execution = WorkflowExecution(
                id=str(uuid.uuid4()),
                workflow_id=workflow.id,
                tenant_id=tenant_id,
                session_id=request.session_id,
                user_identifier=user_identifier,
                status=ExecutionStatus.RUNNING,
                current_step_id=first_step.id,
                variables=variables,
                total_steps=len(definition.steps)
            )

            self.db.add(execution)
            self.db.commit()
            self.db.refresh(execution)

            # Save the initial state
            await self.state_manager.save_state(
                session_id=request.session_id,
                execution_id=execution.id,
                workflow_id=workflow.id,
                tenant_id=tenant_id,
                current_step_id=first_step.id,
                variables=variables
            )

            # Update workflow usage
            workflow.usage_count += 1
            workflow.last_used_at = datetime.utcnow()
            self.db.commit()

            logger.info(f"Started workflow execution {execution.id} for workflow {workflow.id}")

            # Execute the first step and capture the result
            first_step_result = None
            if first_step.type != SchemaStepType.INPUT and first_step.type != SchemaStepType.CHOICE:
                # Execute non-interactive steps immediately
                first_step_result = await self._execute_step_internal(execution, first_step, definition, variables)

                # If the first step completed and has next_step that's interactive, prepare it
                if first_step_result and first_step_result.next_step_id and not first_step_result.workflow_completed:
                    next_step = WorkflowParser.get_step_by_id(definition, first_step_result.next_step_id)
                    if next_step and next_step.type in [SchemaStepType.CHOICE, SchemaStepType.INPUT]:
                        # Save the first message
                        first_message = first_step_result.message

                        # Prepare the interactive step for display
                        if next_step.type == SchemaStepType.CHOICE:
                            result = await self._execute_choice_step(next_step, variables, definition)
                            # Combine first message with choice message
                            combined_message = f"{first_message}\n\n{result.get('message')}" if result.get('message') else first_message
                            first_step_result = StepExecutionResult(
                                success=True,
                                step_id=next_step.id,
                                step_type=next_step.type,
                                message=combined_message,
                                choices=result.get("choices"),
                                input_required=result.get("input_required"),
                                next_step_id=None,
                                workflow_completed=False
                            )

                            # Update state to reflect we're waiting for choice
                            await self.state_manager.advance_step(
                                execution.session_id,
                                next_step.id,
                                waiting_for_input="choice"
                            )
                        elif next_step.type == SchemaStepType.INPUT:
                            result = await self._execute_input_step(next_step, variables, definition)
                            # Combine first message with input prompt
                            combined_message = f"{first_message}\n\n{result.get('message')}" if result.get('message') else first_message
                            first_step_result = StepExecutionResult(
                                success=True,
                                step_id=next_step.id,
                                step_type=next_step.type,
                                message=combined_message,
                                input_required=result.get("input_required"),
                                next_step_id=None,
                                workflow_completed=False
                            )

                            # Update state to reflect we're waiting for input
                            await self.state_manager.advance_step(
                                execution.session_id,
                                next_step.id,
                                waiting_for_input="input"
                            )
            else:
                # For interactive steps (input/choice), just prepare them for display
                if first_step.type == SchemaStepType.CHOICE:
                    result = await self._execute_choice_step(first_step, variables, definition)
                    first_step_result = StepExecutionResult(
                        success=True,
                        step_id=first_step.id,
                        step_type=first_step.type,
                        message=result.get("message"),
                        choices=result.get("choices"),
                        input_required=result.get("input_required"),
                        next_step_id=None,
                        workflow_completed=False
                    )
                elif first_step.type == SchemaStepType.INPUT:
                    result = await self._execute_input_step(first_step, variables, definition)
                    first_step_result = StepExecutionResult(
                        success=True,
                        step_id=first_step.id,
                        step_type=first_step.type,
                        message=result.get("message"),
                        input_required=result.get("input_required"),
                        next_step_id=None,
                        workflow_completed=False
                    )

            return self._to_execution_response(execution, first_step_result)

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to start execution: {e}")
            raise

    async def execute_step(
        self,
        request: ExecutionStepRequest,
        tenant_id: str
    ) -> StepExecutionResult:
        """
        Execute the next step in a workflow.

        Args:
            request: Step execution request
            tenant_id: Tenant ID

        Returns:
            Step execution result
        """
        try:
            # Get execution
            execution = self.db.query(WorkflowExecution).filter(
                WorkflowExecution.id == request.execution_id,
                WorkflowExecution.tenant_id == tenant_id
            ).first()

            if not execution:
                logger.error(f"Execution {request.execution_id} not found")
                raise WorkflowExecutionError(f"Execution {request.execution_id} not found")

            if execution.status != ExecutionStatus.RUNNING:
                logger.error(f"Execution is not running (status: {execution.status})")
                raise WorkflowExecutionError(f"Execution is not running (status: {execution.status})")

            # Get workflow and definition
            workflow = self.db.query(Workflow).filter(
                Workflow.id == execution.workflow_id
            ).first()

            if not workflow:
                logger.error(f"Workflow {execution.workflow_id} not found")
                raise WorkflowNotFoundError(f"Workflow {execution.workflow_id} not found")

            logger.info(f"Executing Workflow {workflow.id}, Step {execution.id}")

            definition = WorkflowParser.parse_from_dict(workflow.definition)

            # Get the current step
            current_step = WorkflowParser.get_step_by_id(definition, execution.current_step_id)
            if not current_step:
                raise StepExecutionError(execution.current_step_id, "Step not found in workflow definition")

            # Get current variables from the state
            state = await self.state_manager.get_state(request.session_id)
            if not state:
                raise WorkflowStateError(f"No state found for session {request.session_id}")

            variables = state.get("variables", {})
            logger.info(f"variables: {variables}")

            # Process user input if provided
            if request.user_input:
                logger.info(f"XXX Current step {current_step}")
                logger.info(f"XXXXX Request Input {request.user_input}")
                logger.info(f"XXXXXXXXX Variables {variables}")

                variables = self._process_user_input(current_step, request.user_input, variables)
                logger.info(f"Variables saved to state after processing user input new variable {variables}")
                # Save updated variables to state immediately (same as user_choice handling)
                await self.state_manager.update_variables(request.session_id, variables)


            if request.user_choice:
                logger.info(f"BEFORE _process_user_choice: variables keys = {list(variables.keys())}")
                variables = self._process_user_choice(current_step, request.user_choice, variables)
                logger.info(f"AFTER _process_user_choice: variables keys = {list(variables.keys())}")
                logger.info(f"__selected_option_next_step = {variables.get('__selected_option_next_step')}")

                # Save updated variables to state immediately so they're available in _execute_step_internal
                await self.state_manager.update_variables(request.session_id, variables)
                logger.info(f"Variables saved to state successfully")

            # Update context if provided
            if request.context:
                variables = VariableResolver.merge_variables(variables, request.context)

            # Execute the step
            result = await self._execute_step_internal(execution, current_step, definition, variables)

            # Update execution progress
            execution.steps_completed += 1
            self.db.commit()

            # If user provided input/choice on an INPUT/CHOICE step, manually set next_step_id for auto-execution
            # This is needed because INPUT/CHOICE steps don't return next_step_id when displaying prompts
            if (current_step.type == SchemaStepType.INPUT and request.user_input):
                if not result.next_step_id and current_step.next_step:
                    result.next_step_id = current_step.next_step
                    logger.info(f"User input provided, setting next_step_id to {current_step.next_step}")

            # If this was a choice/input step and we have a next_step, execute it automatically
            if (current_step.type in [SchemaStepType.CHOICE, SchemaStepType.INPUT] and
                result.next_step_id and not result.workflow_completed and
                (request.user_choice or request.user_input)):

                logger.info(
                    f"User interaction completed on {current_step.type.value} step, "
                    f"next_step_id={result.next_step_id}, "
                    f"user_choice={request.user_choice}, "
                    f"user_input={request.user_input}"
                )

                # Loop through non-interactive steps until we reach an interactive step
                current_next_step_id = result.next_step_id
                max_iterations = 50  # Prevent infinite loops
                iterations = 0
                final_result = result

                while current_next_step_id and iterations < max_iterations:
                    iterations += 1

                    # Get the next step
                    next_step = WorkflowParser.get_step_by_id(definition, current_next_step_id)

                    if not next_step:
                        logger.warning(f"Next step {current_next_step_id} not found in workflow definition")
                        break

                    logger.info(
                        f"Auto-executing step {iterations}: id={next_step.id}, "
                        f"type={next_step.type.value}"
                    )

                    # Get updated variables from state
                    updated_state = await self.state_manager.get_state(request.session_id)
                    if updated_state:
                        variables = updated_state.get("variables", {})

                    # Execute the next step
                    next_result = await self._execute_step_internal(execution, next_step, definition, variables)
                    execution.steps_completed += 1
                    self.db.commit()

                    logger.info(
                        f"Step executed: step_id={next_result.step_id}, "
                        f"step_type={next_result.step_type.value}, "
                        f"completed={next_result.workflow_completed}, "
                        f"has_message={bool(next_result.message)}, "
                        f"next_step_id={next_result.next_step_id}"
                    )

                    final_result = next_result

                    # If workflow is completed, stop
                    if next_result.workflow_completed:
                        logger.info("Workflow completed, stopping auto-execution")
                        # If the completion step has no message, provide a default completion message
                        if not next_result.message:
                            logger.info("Workflow completed with no message, adding default completion message")
                            final_result = StepExecutionResult(
                                success=next_result.success,
                                step_id=next_result.step_id,
                                step_type=next_result.step_type,
                                workflow_id=next_result.workflow_id,
                                message="Thank you! Your responses have been recorded.",
                                workflow_completed=True
                            )
                        break

                    # If this is an interactive step, always stop - these require user interaction
                    # Interactive steps: MESSAGE, CHOICE, INPUT
                    if next_step.type in [SchemaStepType.MESSAGE, SchemaStepType.CHOICE, SchemaStepType.INPUT]:
                        # Always stop at interactive steps that require user interaction
                        logger.info(f"Reached interactive step {next_step.type.value}, stopping auto-execution")
                        break

                    # If this is a non-interactive step (CONDITION, ACTION, DELAY) and has next_step, continue
                    if next_result.next_step_id:
                        current_next_step_id = next_result.next_step_id
                        logger.info(f"Non-interactive step, continuing to {current_next_step_id}")
                    else:
                        logger.info("No more steps to execute")
                        break

                if iterations >= max_iterations:
                    logger.error(f"Auto-execution exceeded maximum iterations ({max_iterations})")

                return final_result

            return result

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to execute step: {e}")
            raise

    async def cancel_execution(self, execution_id: str, tenant_id: str) -> bool:
        """
        Cancel a running workflow execution.

        Args:
            execution_id: Execution ID
            tenant_id: Tenant ID

        Returns:
            True if canceled successfully
        """
        try:
            execution = self.db.query(WorkflowExecution).filter(
                WorkflowExecution.id == execution_id,
                WorkflowExecution.tenant_id == tenant_id
            ).first()

            if not execution:
                raise WorkflowExecutionError(f"Execution {execution_id} not found")

            if execution.status != ExecutionStatus.RUNNING:
                raise WorkflowExecutionError(f"Cannot cancel execution with status: {execution.status}")

            # Update execution status
            execution.status = ExecutionStatus.CANCELLED
            execution.completed_at = datetime.utcnow()

            self.db.commit()

            # Clean up state
            await self.state_manager.delete_state(execution.session_id)

            logger.info(f"Cancelled execution {execution_id}")
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to cancel execution {execution_id}: {e}")
            raise

    async def get_execution(self, execution_id: str, tenant_id: str) -> WorkflowExecutionResponse:
        """
        Get execution details.

        Args:
            execution_id: Execution ID
            tenant_id: Tenant ID

        Returns:
            Execution response
        """
        execution = self.db.query(WorkflowExecution).filter(
            WorkflowExecution.id == execution_id,
            WorkflowExecution.tenant_id == tenant_id
        ).first()

        if not execution:
            raise WorkflowExecutionError(f"Execution {execution_id} not found")

        return self._to_execution_response(execution)

    def list_executions(
        self,
        tenant_id: str,
        page: int = 1,
        size: int = 10,
        workflow_id: Optional[str] = None,
        status: Optional[str] = None
    ) -> ExecutionList:
        """
        List workflow executions for a tenant.

        Args:
            tenant_id: Tenant ID
            page: Page number
            size: Page size
            workflow_id: Filter by workflow ID
            status: Filter by status

        Returns:
            Paginated execution list
        """
        query = self.db.query(WorkflowExecution).filter(
            WorkflowExecution.tenant_id == tenant_id
        )

        if workflow_id:
            query = query.filter(WorkflowExecution.workflow_id == workflow_id)
        if status:
            query = query.filter(WorkflowExecution.status == status)

        total = query.count()

        offset = (page - 1) * size
        executions = query.order_by(WorkflowExecution.started_at.desc()).offset(offset).limit(size).all()

        execution_summaries = [self._to_execution_summary(e) for e in executions]

        return ExecutionList(
            executions=execution_summaries,
            total=total,
            page=page,
            size=size
        )

    async def _execute_step_internal(
        self,
        execution: WorkflowExecution,
        step,
        definition,
        variables: Dict[str, Any]
    ) -> StepExecutionResult:
        """Execute a single workflow step"""
        step_start_time = datetime.utcnow()

        try:
            # Create step execution record
            step_execution = StepExecution(
                id=str(uuid.uuid4()),
                execution_id=execution.id,
                workflow_id=execution.workflow_id,
                tenant_id=execution.tenant_id,
                step_id=step.id,
                step_type=StepType(step.type.value),
                step_config=step.model_dump(),
                input_data=variables,
                status=ExecutionStatus.RUNNING
            )

            self.db.add(step_execution)
            self.db.commit()

            # Execute based on step type
            if step.type == SchemaStepType.MESSAGE:
                result = await self._execute_message_step(step, variables, definition)
            elif step.type == SchemaStepType.CHOICE:
                logger.info(f"About to execute CHOICE step {step.id}, variables keys = {list(variables.keys())}, __selected_option_next_step = {variables.get('__selected_option_next_step')}")
                result = await self._execute_choice_step(step, variables, definition)
                logger.info(f"CHOICE step result: next_step_id={result.get('next_step_id')}, has_choices={bool(result.get('choices'))}")
            elif step.type == SchemaStepType.INPUT:
                result = await self._execute_input_step(step, variables, definition)
            elif step.type == SchemaStepType.CONDITION:
                result = await self._execute_condition_step(step, variables, definition)
            elif step.type == SchemaStepType.ACTION:
                result = await self._execute_action_step(step, variables, execution, definition)
            elif step.type == SchemaStepType.DELAY:
                result = await self._execute_delay_step(step, variables, definition)
            else:
                raise StepExecutionError(step.id, f"Unsupported step type: {step.type}")

            # Update step execution record
            step_execution.status = ExecutionStatus.COMPLETED
            step_execution.output_data = result
            step_execution.completed_at = datetime.utcnow()
            step_execution.duration_ms = int(
                (step_execution.completed_at - step_start_time).total_seconds() * 1000
            )

            # Update execution state
            if result.get("next_step_id"):
                execution.current_step_id = result["next_step_id"]
                # Pass the potentially modified variables to advance_step
                # This is important because step execution may have popped temporary flags
                await self.state_manager.advance_step(
                    execution.session_id,
                    result["next_step_id"],
                    waiting_for_input=result.get("waiting_for_input"),
                    variables=variables
                )
            elif result.get("workflow_completed"):
                execution.status = ExecutionStatus.COMPLETED
                execution.completed_at = datetime.utcnow()
                # Mark state as completed instead of deleting - it will expire naturally via TTL
                await self.state_manager.mark_completed(execution.session_id)

            # Update variables if changed
            if result.get("variables_updated"):
                variables.update(result["variables_updated"])
                execution.variables = variables
                await self.state_manager.update_variables(execution.session_id, variables)

            self.db.commit()

            logger.debug(f"Executed step {step.id} in execution {execution.id}")

            return StepExecutionResult(
                success=True,
                step_id=step.id,
                step_type=step.type,
                workflow_id=execution.workflow_id,
                message=result.get("message"),
                choices=result.get("choices"),
                input_required=result.get("input_required"),
                next_step_id=result.get("next_step_id"),
                workflow_completed=result.get("workflow_completed", False),
                variables_updated=result.get("variables_updated"),
                metadata=result.get("metadata")
            )

        except Exception as e:
            # Update step execution record with error
            step_execution.status = ExecutionStatus.FAILED
            step_execution.error_message = str(e)
            step_execution.completed_at = datetime.utcnow()

            # Mark execution as failed
            execution.status = ExecutionStatus.FAILED
            execution.error_message = str(e)
            execution.completed_at = datetime.utcnow()

            self.db.commit()

            logger.error(f"Step execution failed: {e}")
            raise StepExecutionError(step.id, str(e))

    async def _execute_message_step(self, step, variables: Dict[str, Any], definition) -> Dict[str, Any]:
        """Execute a message step"""
        message = VariableResolver.resolve_content(step.content, variables)

        # Check if next_step is None OR doesn't exist in the workflow
        workflow_completed = False
        next_step_id = step.next_step if step.next_step else None
        variables_updated = None

        if not next_step_id:
            workflow_completed = True
            # Set completion flag in variables so it propagates through state
            variables["__workflow_completed"] = True
            variables_updated = {"__workflow_completed": True}
            logger.info("MESSAGE step completes workflow - setting __workflow_completed flag")
        else:
            # Check if the next_step actually exists
            next_step_exists = WorkflowParser.get_step_by_id(definition, next_step_id) is not None
            if not next_step_exists:
                logger.info(f"MESSAGE step next_step '{next_step_id}' does not exist, marking workflow as completed")
                workflow_completed = True
                next_step_id = None
                # Set completion flag in variables so it propagates through state
                variables["__workflow_completed"] = True
                variables_updated = {"__workflow_completed": True}

        return {
            "message": message,
            "next_step_id": next_step_id,
            "workflow_completed": workflow_completed,
            "variables_updated": variables_updated
        }

    async def _execute_choice_step(self, step, variables: Dict[str, Any], definition) -> Dict[str, Any]:
        """Execute a choice step"""

        # Check if user has already made a choice (stored by _process_user_choice)
        selected_option_next_step = variables.get('__selected_option_next_step')  # Don't pop yet

        if selected_option_next_step:
            # User has made a choice, proceed to the option's next_step
            # NOW pop it since we're using it
            variables.pop('__selected_option_next_step', None)
            # Check if the next_step exists
            next_step_exists = WorkflowParser.get_step_by_id(definition, selected_option_next_step) is not None
            if not next_step_exists:
                logger.info(f"CHOICE option next_step '{selected_option_next_step}' does not exist, marking workflow as completed")
                return {
                    "next_step_id": None,
                    "workflow_completed": True
                }
            # Don't return the choice message - just advance to next step
            # The next step will provide its own message
            return {
                "next_step_id": selected_option_next_step,
                "workflow_completed": False
            }
        elif '__choice_made' in variables:
            # User made a choice but option didn't specify next_step, use step-level next_step
            variables.pop('__choice_made', None)
            # Treat empty string as None
            next_step_id = step.next_step if step.next_step else None
            workflow_completed = False
            if not next_step_id:
                workflow_completed = True
            else:
                next_step_exists = WorkflowParser.get_step_by_id(definition, next_step_id) is not None
                if not next_step_exists:
                    logger.info(f"CHOICE step next_step '{next_step_id}' does not exist, marking workflow as completed")
                    workflow_completed = True
                    next_step_id = None
            # Don't return the choice message - just advance to next step
            return {
                "next_step_id": next_step_id,
                "workflow_completed": workflow_completed
            }
        elif f'__choice_step_completed_{step.id}' in variables:
            # This choice step was already completed - MUST check BEFORE variable check
            # This prevents re-executing the choice step even if variable is set
            logger.info(f"Choice step {step.id} already completed, preventing re-display")
            # Workflow should already be marked as completed
            return {
                "next_step_id": None,
                "workflow_completed": True
            }
        elif step.variable and step.variable in variables and variables.get(step.variable) and f'__choice_step_completed_{step.id}' not in variables:
            # Choice variable already set with a non-empty value
            # This means user already made a choice in a previous interaction
            # Check if we have the selected option's next_step stored
            logger.info(f"Choice already made for variable '{step.variable}', value='{variables.get(step.variable)}'")

            # Since choice was already made, look for the selected option's next_step
            selected_next_step = None
            if step.options:
                user_choice_value = variables.get(step.variable)
                for option in step.options:
                    if hasattr(option, 'value') and hasattr(option, 'next_step'):
                        if option.value == user_choice_value or option.text == user_choice_value:
                            selected_next_step = option.next_step
                            logger.info(f"Found matching option with next_step: {selected_next_step}")
                            break

            # If we found the option's next_step, use it; otherwise mark as completed
            if selected_next_step:
                next_step_exists = WorkflowParser.get_step_by_id(definition, selected_next_step) is not None
                if next_step_exists:
                    return {
                        "next_step_id": selected_next_step,
                        "workflow_completed": False
                    }

            # No valid next_step found, mark workflow as completed
            logger.info(f"No valid next_step found for completed choice, marking workflow as completed")
            return {
                "next_step_id": None,
                "workflow_completed": True
            }
        else:
            # No choice yet, present options and wait for input
            # Return choice text for display
            message = VariableResolver.resolve_content(step.content, variables)
            choices = []
            if step.options:
                for option in step.options:
                    # If option is a ChoiceOption object, use its text field
                    if hasattr(option, 'text'):
                        choices.append(VariableResolver.resolve_content(option.text, variables))
                    else:
                        # Fallback for string options (backward compatibility)
                        choices.append(VariableResolver.resolve_content(option, variables))

            return {
                "message": message,
                "choices": choices,
                "input_required": "choice",
                "waiting_for_input": "choice"
            }

    async def _execute_input_step(self, step, variables: Dict[str, Any], definition) -> Dict[str, Any]:
        """Execute an input step"""
        # Check if user has already provided input (stored by _process_user_input)
        if step.variable and step.variable in variables and variables.get(step.variable):
            # Input already provided, advance to next step
            logger.info(f"Input already provided for variable '{step.variable}', value='{variables.get(step.variable)}', advancing to next step")
            next_step_id = step.next_step if step.next_step else None
            workflow_completed = False
            if not next_step_id:
                workflow_completed = True
            else:
                next_step_exists = WorkflowParser.get_step_by_id(definition, next_step_id) is not None
                if not next_step_exists:
                    logger.info(f"INPUT step next_step '{next_step_id}' does not exist, marking workflow as completed")
                    workflow_completed = True
                    next_step_id = None
            return {
                "next_step_id": next_step_id,
                "workflow_completed": workflow_completed
            }
        else:
            # No input yet, present prompt and wait for input
            # DO NOT return next_step_id - this prevents premature step advancement
            message = VariableResolver.resolve_content(step.content, variables)
            return {
                "message": message,
                "input_required": "text",
                "waiting_for_input": "text"
                # Note: next_step_id is intentionally NOT included here
                # It will be added after user provides input in execute_step()
            }

    async def _execute_condition_step(self, step, variables: Dict[str, Any], definition) -> Dict[str, Any]:
        """Execute a condition step"""
        if not step.condition:
            raise StepExecutionError(step.id, "Condition step missing condition expression")

        condition_result = VariableResolver.evaluate_condition(step.condition, variables)

        logger.info(
            f"Condition step {step.id}: condition='{step.condition}', "
            f"result={condition_result}, "
            f"variables={list(variables.keys())}"
        )

        if condition_result:
            next_step_id = step.next_step
            logger.info(f"Condition TRUE: proceeding to step '{next_step_id}'")
        else:
            # Look for an alternate path or end workflow
            next_step_id = None  # Could implement else_step logic here
            logger.info(f"Condition FALSE: no alternate path, workflow will end")

        # Check if next_step exists (if condition was true)
        workflow_completed = False
        completion_message = None

        if not next_step_id:
            workflow_completed = True
            # Check if step has completion message in metadata for when condition is false
            if not condition_result and step.metadata:
                completion_message = step.metadata.get("completion_message")
                if completion_message:
                    completion_message = VariableResolver.resolve_content(completion_message, variables)
                    logger.info(f"Using custom completion message from step metadata")
        else:
            # Check if the next_step actually exists
            next_step_exists = WorkflowParser.get_step_by_id(definition, next_step_id) is not None
            if not next_step_exists:
                logger.info(f"CONDITION step next_step '{next_step_id}' does not exist, marking workflow as completed")
                workflow_completed = True
                next_step_id = None

        return {
            "condition_result": condition_result,
            "next_step_id": next_step_id,
            "workflow_completed": workflow_completed,
            "message": completion_message  # Include optional completion message
        }

    async def _execute_action_step(self, step, variables: Dict[str, Any], execution, definition) -> Dict[str, Any]:
        """Execute an action step"""
        if not step.action:
            raise StepExecutionError(step.id, "Action step missing action type")

        # Execute the action
        action_result = await self.action_service.execute_action(
            action_type=step.action,
            action_params=step.params or {},
            variables=variables,
            tenant_id=execution.tenant_id,
            execution_id=execution.id
        )

        # Check if next_step is None OR doesn't exist in the workflow (e.g., "End Workflow")
        # Both cases mean the workflow should complete
        workflow_completed = False
        next_step_id = step.next_step

        if not next_step_id:
            # No next step specified - workflow ends
            workflow_completed = True
            next_step_id = None
        else:
            # Check if the next_step actually exists in the workflow definition
            next_step_exists = WorkflowParser.get_step_by_id(definition, next_step_id) is not None
            if not next_step_exists:
                # next_step references non-existent step (e.g., "End Workflow") - treat as completion
                logger.info(f"ACTION step next_step '{next_step_id}' does not exist, marking workflow as completed")
                workflow_completed = True
                next_step_id = None  # Don't try to navigate to non-existent step

        return {
            "action_result": action_result,
            "next_step_id": next_step_id,
            "workflow_completed": workflow_completed
        }

    async def _execute_delay_step(self, step, variables: Dict[str, Any], definition) -> Dict[str, Any]:
        """Execute a delay step"""
        # For now, just continue to next step
        # In production, this would schedule continuation

        # Check if next_step is None OR doesn't exist in the workflow
        workflow_completed = False
        next_step_id = step.next_step

        if not next_step_id:
            workflow_completed = True
        else:
            next_step_exists = WorkflowParser.get_step_by_id(definition, next_step_id) is not None
            if not next_step_exists:
                logger.info(f"DELAY step next_step '{next_step_id}' does not exist, marking workflow as completed")
                workflow_completed = True
                next_step_id = None

        return {
            "delay_processed": True,
            "next_step_id": next_step_id,
            "workflow_completed": workflow_completed
        }

    def _process_user_input(self, step, user_input: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        """Process user input for input steps"""
        if step.variable:
            # Set the variable directly to the user's input (same as choice processing)
            variables = VariableResolver.set_variable(variables, step.variable, user_input)
            logger.info(f"Set variable '{step.variable}' = '{user_input}'")

        return variables

    def _process_user_choice(self, step, user_choice: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        """Process user choice for choice steps and determine next step based on selected option"""
        logger.debug(f"Processing user choice: '{user_choice}' for step {step.id}")

        if step.variable:
            variables = VariableResolver.set_variable(variables, step.variable, user_choice)

        # Store the selected option's next_step for branching logic
        # This will be picked up in the step execution flow
        choice_matched = False
        if step.options:
            for option in step.options:
                # Match by value or text
                if hasattr(option, 'value') and hasattr(option, 'text'):
                    # ChoiceOption object
                    logger.debug(f"Checking option: text='{option.text}', value='{option.value}', next_step='{option.next_step}'")
                    if option.value == user_choice or option.text == user_choice:
                        logger.info(f"Choice matched! Setting next_step to: {option.next_step}")
                        if option.next_step:
                            variables['__selected_option_next_step'] = option.next_step
                        choice_matched = True
                        break
                elif option == user_choice:
                    # String option (backward compatibility)
                    logger.debug(f"Checking string option: '{option}'")
                    choice_matched = True
                    break

        # Mark that a choice was made (for fallback to step-level next_step)
        if choice_matched:
            variables['__choice_made'] = True
            # Also track this specific choice step as completed
            # This handles re-execution for choice steps without variables
            variables[f'__choice_step_completed_{step.id}'] = True
            logger.debug(f"Choice processing complete. Variables now include: {list(variables.keys())}")
        else:
            logger.warning(f"No option matched for user_choice: '{user_choice}'")

        return variables

    def _to_execution_response(
        self,
        execution: WorkflowExecution,
        first_step_result: Optional[StepExecutionResult] = None
    ) -> WorkflowExecutionResponse:
        """Convert execution model to response"""
        return WorkflowExecutionResponse(
            id=execution.id,
            workflow_id=execution.workflow_id,
            tenant_id=execution.tenant_id,
            session_id=execution.session_id,
            user_identifier=execution.user_identifier,
            status=execution.status,
            current_step_id=execution.current_step_id,
            variables=execution.variables or {},
            started_at=execution.started_at,
            completed_at=execution.completed_at,
            error_message=execution.error_message,
            steps_completed=execution.steps_completed,
            total_steps=execution.total_steps,
            first_step_result=first_step_result
        )

    def _to_execution_summary(self, execution: WorkflowExecution) -> ExecutionSummary:
        """Convert execution model to summary"""
        return ExecutionSummary(
            id=execution.id,
            workflow_id=execution.workflow_id,
            session_id=execution.session_id,
            user_identifier=execution.user_identifier,
            status=execution.status,
            steps_completed=execution.steps_completed,
            total_steps=execution.total_steps,
            started_at=execution.started_at,
            completed_at=execution.completed_at
        )