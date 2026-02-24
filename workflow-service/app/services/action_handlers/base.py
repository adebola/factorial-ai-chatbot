"""
Action Handler Base - Abstract Interface

Defines the contract that all action handlers must implement.
Mirrors the StepExecutor strategy pattern for action dispatching.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class ActionHandler(ABC):
    """
    Abstract base class for action handlers.

    Each concrete handler implements execute() for a specific action type.
    """

    @property
    @abstractmethod
    def action_type(self) -> str:
        """Return the action type this handler handles (e.g. 'log', 'send_email')"""
        pass

    @abstractmethod
    async def execute(
        self,
        params: Dict[str, Any],
        tenant_id: str,
        execution_id: str,
        variables: Dict[str, Any],
        execution_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute the action with resolved parameters.

        Args:
            params: Resolved action parameters (variables already substituted)
            tenant_id: Tenant ID
            execution_id: Execution ID
            variables: Current workflow variables
            execution_context: Optional execution context (contains user_access_token, etc.)

        Returns:
            Dict with at least {"success": True/False, ...}

        Raises:
            ActionExecutionError: If execution fails
        """
        pass

    def get_schema(self) -> Dict[str, Any]:
        """
        Return the parameter schema for this action type.
        Used for API discovery and documentation.
        """
        return {}
