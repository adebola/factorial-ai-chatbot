"""
Action Handlers - Strategy Pattern Implementation

Registry of action handlers that replace the if-elif dispatch chain
in ActionService. Mirrors the StepExecutor pattern.
"""

from typing import Dict, Optional, List

from .base import ActionHandler
from .log_handler import LogActionHandler
from .send_email_handler import SendEmailActionHandler
from .api_call_handler import ApiCallActionHandler

ACTION_HANDLER_REGISTRY: Dict[str, ActionHandler] = {
    "log": LogActionHandler(),
    "send_email": SendEmailActionHandler(),
    "api_call": ApiCallActionHandler(),
}


def get_action_handler(action_type: str) -> Optional[ActionHandler]:
    """Look up a handler by action type string."""
    return ACTION_HANDLER_REGISTRY.get(action_type)


def get_available_action_types() -> List[str]:
    """Return list of registered action type strings."""
    return list(ACTION_HANDLER_REGISTRY.keys())


__all__ = [
    "ActionHandler",
    "LogActionHandler",
    "SendEmailActionHandler",
    "ApiCallActionHandler",
    "ACTION_HANDLER_REGISTRY",
    "get_action_handler",
    "get_available_action_types",
]
