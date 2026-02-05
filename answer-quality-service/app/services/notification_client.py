"""
Notification Client Service

Sends alert notifications via multiple channels (email, webhook, console).
"""

import httpx
import os
from typing import Dict, Any, List, Optional
from datetime import datetime
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class NotificationClient:
    """
    Client for sending notifications through various channels.

    Supported channels:
    - email: Via communications-service
    - webhook: HTTP POST to configured URL
    - console: Console logging (for testing)
    """

    def __init__(self):
        self.communications_service_url = os.environ.get(
            "COMMUNICATIONS_SERVICE_URL",
            "http://localhost:8003"
        )
        self.default_from_email = os.environ.get(
            "ALERT_EMAIL_FROM",
            "alerts@factorialbot.com"
        )
        self.webhook_timeout = 10  # seconds

    async def send_notification(
        self,
        tenant_id: str,
        alert_data: Dict[str, Any],
        channels: List[str],
        recipients: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Send notification through specified channels.

        Args:
            tenant_id: Tenant ID
            alert_data: Alert information
            channels: List of channels (email, webhook, console)
            recipients: Channel-specific recipients
                {
                    "email": ["admin@example.com"],
                    "webhook": "https://hooks.slack.com/..."
                }

        Returns:
            Dict with results per channel
        """
        results = {}

        for channel in channels:
            try:
                if channel == "email":
                    result = await self._send_email(tenant_id, alert_data, recipients)
                    results["email"] = result
                elif channel == "webhook":
                    result = await self._send_webhook(tenant_id, alert_data, recipients)
                    results["webhook"] = result
                elif channel == "console":
                    result = self._log_to_console(tenant_id, alert_data)
                    results["console"] = result
                else:
                    results[channel] = {"success": False, "error": f"Unknown channel: {channel}"}

            except Exception as e:
                logger.error(
                    f"Failed to send notification via {channel}",
                    tenant_id=tenant_id,
                    channel=channel,
                    error=str(e))
                results[channel] = {"success": False, "error": str(e)}

        return results

    async def _send_email(
        self,
        tenant_id: str,
        alert_data: Dict[str, Any],
        recipients: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Send alert via email through communications-service."""

        # Get email recipients
        email_list = []
        if recipients and "email" in recipients:
            email_list = recipients["email"]
        else:
            # Fallback to default (could query tenant settings)
            logger.warning(
                "No email recipients configured for alert",
                tenant_id=tenant_id
            )
            return {"success": False, "error": "No email recipients configured"}

        # Build email content
        subject = f"[Alert] {alert_data.get('rule_name', 'Quality Alert')}"
        body = self._format_email_body(alert_data)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                for email in email_list:
                    response = await client.post(
                        f"{self.communications_service_url}/api/v1/email/send",
                        json={
                            "tenant_id": tenant_id,
                            "to_email": email,
                            "from_email": self.default_from_email,
                            "subject": subject,
                            "body": body,
                            "is_html": False
                        }
                    )

                    if response.status_code != 200:
                        logger.error(
                            f"Failed to send alert email",
                            tenant_id=tenant_id,
                            email=email,
                            status_code=response.status_code,
                            response=response.text
                        )

            logger.info(
                "Alert emails sent successfully",
                tenant_id=tenant_id,
                recipient_count=len(email_list)
            )

            return {
                "success": True,
                "recipients": email_list,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.exception(
                f"Email notification failed: {e}",
                tenant_id=tenant_id)
            return {"success": False, "error": str(e)}

    async def _send_webhook(
        self,
        tenant_id: str,
        alert_data: Dict[str, Any],
        recipients: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Send alert via webhook (e.g., Slack, Discord)."""

        webhook_url = None
        if recipients and "webhook" in recipients:
            webhook_url = recipients["webhook"]

        if not webhook_url:
            logger.warning(
                "No webhook URL configured for alert",
                tenant_id=tenant_id
            )
            return {"success": False, "error": "No webhook URL configured"}

        # Format webhook payload (Slack-compatible format)
        payload = {
            "text": f"*{alert_data.get('rule_name', 'Quality Alert')}*",
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": alert_data.get('rule_name', 'Quality Alert')
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": alert_data.get('message', 'An alert has been triggered.')
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Severity:*\n{alert_data.get('severity', 'warning')}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Tenant:*\n{tenant_id[:8]}..."
                        }
                    ]
                }
            ]
        }

        try:
            async with httpx.AsyncClient(timeout=self.webhook_timeout) as client:
                response = await client.post(webhook_url, json=payload)

                if response.status_code >= 400:
                    logger.error(
                        f"Webhook notification failed",
                        tenant_id=tenant_id,
                        status_code=response.status_code,
                        response=response.text
                    )
                    return {
                        "success": False,
                        "error": f"HTTP {response.status_code}: {response.text}"
                    }

            logger.info(
                "Webhook notification sent successfully",
                tenant_id=tenant_id,
                webhook_url=webhook_url[:50] + "..."
            )

            return {
                "success": True,
                "webhook_url": webhook_url[:50] + "...",
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.exception(
                f"Webhook notification failed: {e}",
                tenant_id=tenant_id)
            return {"success": False, "error": str(e)}

    def _log_to_console(
        self,
        tenant_id: str,
        alert_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Log alert to console (for testing)."""

        logger.warning(
            f"ALERT: {alert_data.get('rule_name', 'Quality Alert')}",
            tenant_id=tenant_id,
            severity=alert_data.get('severity', 'warning'),
            message=alert_data.get('message', ''),
            rule_type=alert_data.get('rule_type', ''),
            alert_data=alert_data
        )

        return {
            "success": True,
            "logged_at": datetime.now().isoformat()
        }

    def _format_email_body(self, alert_data: Dict[str, Any]) -> str:
        """Format alert data as plain text email body."""

        body = f"""
Quality Alert Notification
==========================

Alert: {alert_data.get('rule_name', 'N/A')}
Severity: {alert_data.get('severity', 'warning').upper()}
Type: {alert_data.get('rule_type', 'N/A')}

Message:
{alert_data.get('message', 'No message provided')}

Details:
--------
Triggered At: {alert_data.get('triggered_at', datetime.now().isoformat())}

{self._format_alert_details(alert_data)}

---
This is an automated alert from the Answer Quality & Feedback Service.
"""
        return body.strip()

    def _format_alert_details(self, alert_data: Dict[str, Any]) -> str:
        """Format additional alert details."""

        details = []

        if 'threshold' in alert_data:
            details.append(f"Threshold: {alert_data['threshold']}")

        if 'current_value' in alert_data:
            details.append(f"Current Value: {alert_data['current_value']}")

        if 'sample_size' in alert_data:
            details.append(f"Sample Size: {alert_data['sample_size']}")

        if 'time_period' in alert_data:
            details.append(f"Time Period: {alert_data['time_period']}")

        return "\n".join(details) if details else "No additional details available."


# Singleton instance
notification_client = NotificationClient()
