"""
Action service for executing workflow actions.
Thin facade that resolves variables and delegates to action handlers.
"""

from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from ..core.exceptions import ActionExecutionError
from ..core.logging_config import get_logger
from .variable_resolver import VariableResolver
from .action_handlers import get_action_handler, get_available_action_types, ACTION_HANDLER_REGISTRY

logger = get_logger("action_service")


class ActionService:
    """Service for executing workflow actions"""

    def __init__(self, db: Optional[Session] = None):
        self.db = db

    async def execute_action(
        self,
        action_type: str,
        action_params: Dict[str, Any],
        variables: Dict[str, Any],
        tenant_id: str,
        execution_id: str,
        execution_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute a workflow action.

        Resolves variables in params, then delegates to the appropriate handler.
        """
        try:
            logger.info(f"===== ACTION VARIABLE RESOLUTION =====")
            logger.info(f"Action type: {action_type}")
            logger.info(f"BEFORE resolution - params: {action_params}")
            logger.info(f"Available variables: {variables}")

            resolved_params = self._resolve_action_params(action_params, variables)

            logger.info(f"AFTER resolution - params: {resolved_params}")
            logger.info(f"===== END VARIABLE RESOLUTION =====")

            logger.info(f"Executing action {action_type} for execution {execution_id}")

            handler = get_action_handler(action_type)
            if not handler:
                raise ActionExecutionError(
                    action_type,
                    f"Unknown action type: {action_type}. Available: {get_available_action_types()}"
                )

            return await handler.execute(resolved_params, tenant_id, execution_id, variables, execution_context=execution_context)

        except ActionExecutionError:
            raise
        except Exception as e:
            logger.error(f"Action execution failed: {e}")
            raise ActionExecutionError(action_type, str(e))

    def _resolve_action_params(
        self,
        params: Dict[str, Any],
        variables: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Resolve variables in action parameters (handles nested dicts/lists)"""
        resolved_params = {}

        for key, value in params.items():
            if isinstance(value, str):
                resolved_params[key] = VariableResolver.resolve_content(value, variables)
            elif isinstance(value, dict):
                resolved_params[key] = self._resolve_action_params(value, variables)
            elif isinstance(value, list):
                resolved_params[key] = [
                    VariableResolver.resolve_content(item, variables) if isinstance(item, str) else item
                    for item in value
                ]
            else:
                resolved_params[key] = value

        return resolved_params

    def get_available_actions(self) -> Dict[str, Dict[str, Any]]:
        """Get available actions and their parameter schemas."""
        return {
            handler.action_type: handler.get_schema()
            for handler in ACTION_HANDLER_REGISTRY.values()
        }
