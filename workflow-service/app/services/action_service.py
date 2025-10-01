"""
Action service for executing workflow actions.
Handles various action types like sending emails, webhooks, data operations, etc.
"""
import httpx
import json
import os
from typing import Dict, Any, Optional
from datetime import datetime

from ..core.exceptions import ActionExecutionError
from ..core.logging_config import get_logger
from .variable_resolver import VariableResolver

logger = get_logger("action_service")


class ActionService:
    """Service for executing workflow actions"""

    def __init__(self):
        self.communications_url = os.environ.get("COMMUNICATIONS_SERVICE_URL", "http://localhost:8003")
        self.timeout = 30.0

    async def execute_action(
        self,
        action_type: str,
        action_params: Dict[str, Any],
        variables: Dict[str, Any],
        tenant_id: str,
        execution_id: str
    ) -> Dict[str, Any]:
        """
        Execute a workflow action.

        Args:
            action_type: Type of action to execute
            action_params: Action parameters
            variables: Current workflow variables
            tenant_id: Tenant ID
            execution_id: Execution ID

        Returns:
            Action execution result
        """
        try:
            # Resolve variables in action parameters
            resolved_params = self._resolve_action_params(action_params, variables)

            logger.info(f"Executing action {action_type} for execution {execution_id}")

            # Route to appropriate action handler
            if action_type == "send_email":
                return await self._send_email(resolved_params, tenant_id, execution_id)
            elif action_type == "send_sms":
                return await self._send_sms(resolved_params, tenant_id, execution_id)
            elif action_type == "webhook":
                return await self._call_webhook(resolved_params, tenant_id, execution_id)
            elif action_type == "set_variable":
                return await self._set_variable(resolved_params, variables)
            elif action_type == "delay":
                return await self._delay(resolved_params)
            elif action_type == "create_support_ticket":
                return await self._create_support_ticket(resolved_params, tenant_id, execution_id)
            elif action_type == "log":
                return await self._log_action(resolved_params, tenant_id, execution_id)
            else:
                raise ActionExecutionError(action_type, f"Unknown action type: {action_type}")

        except ActionExecutionError:
            raise
        except Exception as e:
            logger.error(f"Action execution failed: {e}")
            raise ActionExecutionError(action_type, str(e))

    async def _send_email(
        self,
        params: Dict[str, Any],
        tenant_id: str,
        execution_id: str
    ) -> Dict[str, Any]:
        """Send email using communications service"""
        try:
            required_fields = ["to", "subject", "content"]
            for field in required_fields:
                if field not in params:
                    raise ActionExecutionError("send_email", f"Missing required field: {field}")

            email_data = {
                "to": params["to"],
                "subject": params["subject"],
                "content": params["content"],
                "tenant_id": tenant_id,
                "source": f"workflow_execution_{execution_id}",
                "template": params.get("template"),
                "variables": params.get("variables", {})
            }

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.communications_url}/api/v1/email/send",
                    json=email_data,
                    headers={"Content-Type": "application/json"}
                )

                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"Email sent successfully: {result.get('message_id')}")
                    return {
                        "success": True,
                        "message_id": result.get("message_id"),
                        "recipient": params["to"]
                    }
                else:
                    error_detail = response.text
                    raise ActionExecutionError("send_email", f"Email service error: {error_detail}")

        except httpx.RequestError as e:
            raise ActionExecutionError("send_email", f"Failed to connect to email service: {e}")

    async def _send_sms(
        self,
        params: Dict[str, Any],
        tenant_id: str,
        execution_id: str
    ) -> Dict[str, Any]:
        """Send SMS using communications service"""
        try:
            required_fields = ["to", "message"]
            for field in required_fields:
                if field not in params:
                    raise ActionExecutionError("send_sms", f"Missing required field: {field}")

            sms_data = {
                "to": params["to"],
                "message": params["message"],
                "tenant_id": tenant_id,
                "source": f"workflow_execution_{execution_id}"
            }

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.communications_url}/api/v1/sms/send",
                    json=sms_data,
                    headers={"Content-Type": "application/json"}
                )

                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"SMS sent successfully: {result.get('message_id')}")
                    return {
                        "success": True,
                        "message_id": result.get("message_id"),
                        "recipient": params["to"]
                    }
                else:
                    error_detail = response.text
                    raise ActionExecutionError("send_sms", f"SMS service error: {error_detail}")

        except httpx.RequestError as e:
            raise ActionExecutionError("send_sms", f"Failed to connect to SMS service: {e}")

    async def _call_webhook(
        self,
        params: Dict[str, Any],
        tenant_id: str,
        execution_id: str
    ) -> Dict[str, Any]:
        """Call external webhook"""
        try:
            url = params.get("url")
            if not url:
                raise ActionExecutionError("webhook", "Missing required field: url")

            method = params.get("method", "POST").upper()
            headers = params.get("headers", {})
            data = params.get("data", {})

            # Add default headers
            headers.setdefault("Content-Type", "application/json")
            headers.setdefault("User-Agent", f"FactorialBot-Workflow/{execution_id}")

            # Add tenant context to payload
            payload = {
                "tenant_id": tenant_id,
                "execution_id": execution_id,
                "timestamp": datetime.utcnow().isoformat(),
                "data": data
            }

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                if method == "GET":
                    response = await client.get(url, headers=headers, params=payload)
                elif method == "POST":
                    response = await client.post(url, headers=headers, json=payload)
                elif method == "PUT":
                    response = await client.put(url, headers=headers, json=payload)
                elif method == "PATCH":
                    response = await client.patch(url, headers=headers, json=payload)
                else:
                    raise ActionExecutionError("webhook", f"Unsupported HTTP method: {method}")

                logger.info(f"Webhook called: {method} {url} -> {response.status_code}")

                return {
                    "success": True,
                    "status_code": response.status_code,
                    "response_data": response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text,
                    "url": url,
                    "method": method
                }

        except httpx.RequestError as e:
            raise ActionExecutionError("webhook", f"Failed to call webhook: {e}")

    async def _set_variable(
        self,
        params: Dict[str, Any],
        variables: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Set or update workflow variables"""
        try:
            variable_name = params.get("variable")
            value = params.get("value")

            if not variable_name:
                raise ActionExecutionError("set_variable", "Missing required field: variable")

            # Set the variable
            VariableResolver.set_variable(variables, variable_name, value)

            logger.debug(f"Set variable {variable_name} = {value}")

            return {
                "success": True,
                "variable": variable_name,
                "value": value
            }

        except Exception as e:
            raise ActionExecutionError("set_variable", f"Failed to set variable: {e}")

    async def _delay(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Add a delay (for future implementation with task queue)"""
        try:
            delay_seconds = params.get("seconds", 0)
            delay_minutes = params.get("minutes", 0)
            delay_hours = params.get("hours", 0)

            total_seconds = delay_seconds + (delay_minutes * 60) + (delay_hours * 3600)

            if total_seconds <= 0:
                raise ActionExecutionError("delay", "Delay must be greater than 0")

            # For now, just log the delay requirement
            # In a production system, this would schedule the workflow to continue later
            logger.info(f"Delay action: {total_seconds} seconds")

            return {
                "success": True,
                "delay_seconds": total_seconds,
                "note": "Delay action logged - requires task queue implementation for actual delays"
            }

        except Exception as e:
            raise ActionExecutionError("delay", f"Failed to process delay: {e}")

    async def _create_support_ticket(
        self,
        params: Dict[str, Any],
        tenant_id: str,
        execution_id: str
    ) -> Dict[str, Any]:
        """Create a support ticket (placeholder implementation)"""
        try:
            required_fields = ["title", "description"]
            for field in required_fields:
                if field not in params:
                    raise ActionExecutionError("create_support_ticket", f"Missing required field: {field}")

            # In a real implementation, this would integrate with a ticketing system
            ticket_id = f"WF-{execution_id[:8]}-{int(datetime.utcnow().timestamp())}"

            ticket_data = {
                "id": ticket_id,
                "title": params["title"],
                "description": params["description"],
                "priority": params.get("priority", "normal"),
                "category": params.get("category", "workflow"),
                "tenant_id": tenant_id,
                "source": "workflow",
                "execution_id": execution_id,
                "created_at": datetime.utcnow().isoformat()
            }

            logger.info(f"Support ticket created: {ticket_id}")

            return {
                "success": True,
                "ticket_id": ticket_id,
                "ticket_data": ticket_data
            }

        except Exception as e:
            raise ActionExecutionError("create_support_ticket", f"Failed to create ticket: {e}")

    async def _log_action(
        self,
        params: Dict[str, Any],
        tenant_id: str,
        execution_id: str
    ) -> Dict[str, Any]:
        """Log information during workflow execution"""
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

            # Log based on level
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

    def _resolve_action_params(
        self,
        params: Dict[str, Any],
        variables: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Resolve variables in action parameters"""
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
        """
        Get list of available actions and their parameters.

        Returns:
            Dictionary of available actions with their parameter schemas
        """
        return {
            "send_email": {
                "description": "Send an email message",
                "required_params": ["to", "subject", "content"],
                "optional_params": ["template", "variables"],
                "example": {
                    "to": "{{email}}",
                    "subject": "Welcome to our service",
                    "content": "Hello {{name}}, welcome!",
                    "template": "welcome_email",
                    "variables": {"name": "{{user_name}}"}
                }
            },
            "send_sms": {
                "description": "Send an SMS message",
                "required_params": ["to", "message"],
                "optional_params": [],
                "example": {
                    "to": "{{phone}}",
                    "message": "Your verification code is {{code}}"
                }
            },
            "webhook": {
                "description": "Call an external webhook",
                "required_params": ["url"],
                "optional_params": ["method", "headers", "data"],
                "example": {
                    "url": "https://api.example.com/webhook",
                    "method": "POST",
                    "headers": {"Authorization": "Bearer token"},
                    "data": {"user_id": "{{user_id}}", "event": "workflow_completed"}
                }
            },
            "set_variable": {
                "description": "Set or update a workflow variable",
                "required_params": ["variable", "value"],
                "optional_params": [],
                "example": {
                    "variable": "status",
                    "value": "completed"
                }
            },
            "delay": {
                "description": "Add a delay before continuing workflow",
                "required_params": [],
                "optional_params": ["seconds", "minutes", "hours"],
                "example": {
                    "minutes": 5
                }
            },
            "create_support_ticket": {
                "description": "Create a support ticket",
                "required_params": ["title", "description"],
                "optional_params": ["priority", "category"],
                "example": {
                    "title": "User issue: {{issue_type}}",
                    "description": "{{issue_details}}",
                    "priority": "high",
                    "category": "technical"
                }
            },
            "log": {
                "description": "Log information during workflow execution",
                "required_params": [],
                "optional_params": ["message", "level", "data"],
                "example": {
                    "message": "User completed qualification: {{user_email}}",
                    "level": "info",
                    "data": {"score": "{{qualification_score}}"}
                }
            }
        }