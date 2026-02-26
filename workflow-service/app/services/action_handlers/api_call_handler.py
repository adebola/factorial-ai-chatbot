"""
API Call Action Handler

Makes outbound HTTP POST requests to external APIs.
Replaces the old 'webhook' action with a simpler, POST-only interface.
Supports opt-in forwarding of end-user OAuth2 tokens via `forward_user_token: true`.
"""

import json
import httpx
from typing import Dict, Any, Optional

from .base import ActionHandler
from ...core.exceptions import ActionExecutionError
from ...core.logging_config import get_logger

logger = get_logger("api_call_action_handler")


class ApiCallActionHandler(ActionHandler):
    """Handler for 'api_call' action type"""

    TIMEOUT = 30.0
    _client: httpx.AsyncClient = None

    @classmethod
    def _get_client(cls) -> httpx.AsyncClient:
        """Lazy singleton HTTP client with connection pooling."""
        if cls._client is None:
            cls._client = httpx.AsyncClient(
                timeout=cls.TIMEOUT,
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10)
            )
        return cls._client

    @property
    def action_type(self) -> str:
        return "api_call"

    async def execute(
        self,
        params: Dict[str, Any],
        tenant_id: str,
        execution_id: str,
        variables: Dict[str, Any],
        execution_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        url = params.get("url")
        if not url:
            raise ActionExecutionError("api_call", "Missing required field: url")

        body = self._ensure_dict(params.get("body", {}))
        headers = self._ensure_dict(params.get("headers", {}))

        headers.setdefault("Content-Type", "application/json")
        headers.setdefault("User-Agent", f"ChatCraft-Workflow/{execution_id}")

        # Forward user token if: (a) step explicitly opts in, OR (b) workflow requires auth
        should_forward = params.get("forward_user_token") or (
            execution_context and execution_context.get("workflow_requires_auth")
        )
        if should_forward and execution_context:
            user_token = execution_context.get("user_access_token")
            if user_token:
                headers["Authorization"] = f"Bearer {user_token}"
                logger.info(
                    "Forwarding user access token to external API",
                    url=url,
                    execution_id=execution_id
                )
            else:
                logger.warning(
                    "Token forwarding requested but no user_access_token in execution context",
                    url=url,
                    execution_id=execution_id
                )

        try:
            client = self._get_client()
            response = await client.post(url, headers=headers, json=body)

            logger.info(
                "API call completed",
                url=url,
                status_code=response.status_code,
                execution_id=execution_id
            )

            return {
                "success": True,
                "status_code": response.status_code,
                "response_data": (
                    response.json()
                    if response.headers.get("content-type", "").startswith("application/json")
                    else response.text
                ),
                "url": url
            }

        except httpx.RequestError as e:
            raise ActionExecutionError("api_call", f"Failed to call API: {e}")

    @staticmethod
    def _ensure_dict(value) -> dict:
        """Coerce a value to dict — handles JSON strings from the UI."""
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return parsed
            except (json.JSONDecodeError, ValueError):
                pass
        return {}

    def get_schema(self) -> Dict[str, Any]:
        return {
            "description": "Make an outbound HTTP POST request to an external API",
            "required_params": ["url"],
            "optional_params": ["body", "headers", "forward_user_token"],
            "example": {
                "url": "https://api.example.com/webhook",
                "headers": {"Authorization": "Bearer token"},
                "body": {"user_id": "{{user_id}}", "event": "workflow_completed"},
                "forward_user_token": True
            }
        }
