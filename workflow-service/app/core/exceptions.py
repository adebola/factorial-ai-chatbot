"""
Custom exceptions for the workflow service.
"""


class WorkflowException(Exception):
    """Base exception for workflow-related errors"""
    pass


class WorkflowNotFoundError(WorkflowException):
    """Raised when a workflow is not found"""
    pass


class WorkflowValidationError(WorkflowException):
    """Raised when workflow validation fails"""
    pass


class WorkflowExecutionError(WorkflowException):
    """Raised when workflow execution fails"""
    pass


class StepExecutionError(WorkflowExecutionError):
    """Raised when a specific step execution fails"""
    def __init__(self, step_id: str, message: str):
        self.step_id = step_id
        super().__init__(f"Step '{step_id}' failed: {message}")


class WorkflowStateError(WorkflowException):
    """Raised when there's an issue with workflow state"""
    pass


class TenantAccessError(WorkflowException):
    """Raised when tenant access is denied"""
    pass


class ActionExecutionError(WorkflowException):
    """Raised when an action execution fails"""
    def __init__(self, action_type: str, message: str):
        self.action_type = action_type
        super().__init__(f"Action '{action_type}' failed: {message}")


class VariableResolutionError(WorkflowException):
    """Raised when variable resolution fails"""
    def __init__(self, variable_name: str, message: str):
        self.variable_name = variable_name
        super().__init__(f"Variable '{variable_name}' resolution failed: {message}")


class WorkflowTimeoutError(WorkflowExecutionError):
    """Raised when workflow execution times out"""
    pass


class InvalidTriggerError(WorkflowException):
    """Raised when trigger configuration is invalid"""
    pass