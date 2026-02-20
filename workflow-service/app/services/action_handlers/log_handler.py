"""
Log Action Handler

Logs information during workflow execution.
"""

from typing import Dict, Any
from datetime import datetime

from .base import ActionHandler
from ...core.exceptions import ActionExecutionError
from ...core.logging_config import get_logger

logger = get_logger("log_action_handler")


class LogActionHandler(ActionHandler):
    """Handler for 'log' action type"""

    @property
    def action_type(self) -> str:
        return "log"

    async def execute(
        self,
        params: Dict[str, Any],
        tenant_id: str,
        execution_id: str,
        variables: Dict[str, Any]
    ) -> Dict[str, Any]:
        try:
            message = params.get("message", "Workflow log entry")
            level = params.get("level", "info").lower()
            data = params.get("data", {})

            log_entry = {
                "message": message,
                "level": level,
                "tenant_id": tenant_id,
                "execution_id": execution_id,
                "data": data,
                "timestamp": datetime.utcnow().isoformat()
            }

            if level == "debug":
                logger.debug(message, **data)
            elif level == "warning":
                logger.warning(message, **data)
            elif level == "error":
                logger.error(message, **data)
            else:
                logger.info(message, **data)

            return {
                "success": True,
                "logged": True,
                "log_entry": log_entry
            }

        except Exception as e:
            raise ActionExecutionError("log", f"Failed to log: {e}")

    def get_schema(self) -> Dict[str, Any]:
        return {
            "description": "Log information during workflow execution",
            "required_params": [],
            "optional_params": ["message", "level", "data"],
            "example": {
                "message": "User completed qualification: {{user_email}}",
                "level": "info",
                "data": {"score": "{{qualification_score}}"}
            }
        }
