"""
Send Email Action Handler

Sends email via RabbitMQ (asynchronous, non-blocking).
"""

from typing import Dict, Any

from .base import ActionHandler
from ...core.exceptions import ActionExecutionError
from ...core.logging_config import get_logger
from ..rabbitmq_publisher import get_rabbitmq_publisher

logger = get_logger("send_email_action_handler")


class SendEmailActionHandler(ActionHandler):
    """Handler for 'send_email' action type"""

    @property
    def action_type(self) -> str:
        return "send_email"

    async def execute(
        self,
        params: Dict[str, Any],
        tenant_id: str,
        execution_id: str,
        variables: Dict[str, Any]
    ) -> Dict[str, Any]:
        try:
            required_fields = ["to", "subject", "content"]
            for field in required_fields:
                if field not in params:
                    raise ActionExecutionError("send_email", f"Missing required field: {field}")

            publisher = get_rabbitmq_publisher()
            result = await publisher.publish_email(
                tenant_id=tenant_id,
                to_email=params["to"],
                subject=params["subject"],
                html_content=params["content"],
                text_content=params.get("text_content"),
                to_name=params.get("to_name"),
                template_id=params.get("template"),
                template_data=params.get("variables", {})
            )

            if result["success"]:
                logger.info(f"Email queued successfully: {result['message_id']}")
                return {
                    "success": True,
                    "message_id": result["message_id"],
                    "recipient": params["to"],
                    "queued": True
                }
            else:
                error_msg = result.get('error', 'Unknown error')
                if "Connection" in error_msg or "EOF" in error_msg:
                    error_msg = f"Unable to connect to messaging service. Please try again later. (Technical details: {error_msg})"
                raise ActionExecutionError("send_email", f"Failed to queue email: {error_msg}")

        except ActionExecutionError:
            raise
        except Exception as e:
            logger.exception(f"Unexpected error in send_email action: {e}")
            raise ActionExecutionError("send_email", f"An unexpected error occurred while sending email. Please contact support if this persists.")

    def get_schema(self) -> Dict[str, Any]:
        return {
            "description": "Send an email message via communications service",
            "required_params": ["to", "subject", "content"],
            "optional_params": ["to_name", "text_content", "template", "variables"],
            "example": {
                "to": "{{email}}",
                "subject": "Welcome to our service",
                "content": "Hello {{name}}, welcome!",
                "to_name": "{{user_name}}",
                "template": "welcome_email",
                "variables": {"name": "{{user_name}}"}
            }
        }
