"""
RabbitMQ Publisher for asynchronous email and SMS messaging.
Publishes messages to communications service queues.
"""
import json
import os
import uuid
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import pika
from pika.exceptions import AMQPConnectionError, AMQPChannelError

from ..core.logging_config import get_logger

logger = get_logger("rabbitmq_publisher")


class RabbitMQPublisher:
    """
    Singleton RabbitMQ publisher for workflow service.
    Publishes email and SMS messages to communications service queues.
    """

    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # Only initialize once
        if hasattr(self, '_initialized'):
            return

        self.host = os.environ.get("RABBITMQ_HOST", "localhost")
        self.port = int(os.environ.get("RABBITMQ_PORT", "5672"))
        self.username = os.environ.get("RABBITMQ_USERNAME", "guest")
        self.password = os.environ.get("RABBITMQ_PASSWORD", "guest")
        self.exchange = os.environ.get("RABBITMQ_EXCHANGE", "communications-exchange")

        self.connection = None
        self.channel = None

        # Thread pool for blocking pika operations
        self._executor = ThreadPoolExecutor(max_workers=5)

        self._initialized = True
        logger.info("RabbitMQ Publisher initialized")

    def _connect(self) -> bool:
        """Establish connection to RabbitMQ"""
        try:
            # Force close any stale connections to prevent EOF errors
            if self.connection:
                try:
                    if not self.connection.is_closed:
                        # Connection exists and is open
                        return True
                    # Connection exists but is closed, clean it up
                    self.connection.close()
                except Exception as e:
                    logger.warning(f"Error checking/closing stale connection: {e}")
                finally:
                    # Always reset connection objects when reconnecting
                    self.connection = None
                    self.channel = None

            credentials = pika.PlainCredentials(self.username, self.password)
            parameters = pika.ConnectionParameters(
                host=self.host,
                port=self.port,
                credentials=credentials,
                heartbeat=600,
                blocked_connection_timeout=300
            )

            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()

            # Declare exchange (idempotent)
            self.channel.exchange_declare(
                exchange=self.exchange,
                exchange_type='topic',
                durable=True
            )

            logger.info(f"Connected to RabbitMQ at {self.host}:{self.port}")
            return True

        except AMQPConnectionError as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            self.connection = None
            self.channel = None
            return False
        except Exception as e:
            logger.error(f"Unexpected error connecting to RabbitMQ: {e}")
            self.connection = None
            self.channel = None
            return False

    def _publish_message(
        self,
        routing_key: str,
        message_data: Dict[str, Any]
    ) -> bool:
        """
        Synchronous message publishing (runs in thread pool).

        Args:
            routing_key: RabbitMQ routing key
            message_data: Message payload

        Returns:
            bool: True if published successfully
        """
        try:
            if not self._connect():
                logger.error("Cannot publish: RabbitMQ connection failed")
                return False

            # Add timestamp
            message_data["queued_at"] = datetime.utcnow().isoformat()

            # Publish message
            self.channel.basic_publish(
                exchange=self.exchange,
                routing_key=routing_key,
                body=json.dumps(message_data),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Persistent message
                    content_type="application/json"
                )
            )

            logger.info(
                f"Message published to '{routing_key}': {message_data.get('message_id', 'unknown')}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to publish message to '{routing_key}': {e}")
            # Try to reconnect on next attempt
            self._disconnect()
            return False

    def _disconnect(self):
        """Close RabbitMQ connection"""
        try:
            if self.channel:
                try:
                    if not self.channel.is_closed:
                        self.channel.close()
                except Exception:
                    pass  # Ignore errors closing channel

            if self.connection:
                try:
                    if not self.connection.is_closed:
                        self.connection.close()
                except Exception:
                    pass  # Ignore errors closing connection

            logger.info("Disconnected from RabbitMQ")
        except Exception as e:
            logger.error(f"Error disconnecting from RabbitMQ: {e}")
        finally:
            # Always reset connection objects
            self.connection = None
            self.channel = None

    async def publish_email(
        self,
        tenant_id: str,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        to_name: Optional[str] = None,
        template_id: Optional[str] = None,
        template_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Publish email message to queue (async, non-blocking).

        Args:
            tenant_id: Tenant identifier
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML email body
            text_content: Plain text email body (optional)
            to_name: Recipient name (optional)
            template_id: Email template ID (optional)
            template_data: Template variables (optional)

        Returns:
            Dict with success status and message_id
        """
        try:
            message_id = str(uuid.uuid4())

            message_data = {
                "message_id": message_id,
                "tenant_id": tenant_id,
                "to_email": to_email,
                "to_name": to_name,
                "subject": subject,
                "html_content": html_content,
                "text_content": text_content,
                "template_id": template_id,
                "template_data": template_data or {}
            }

            # Run blocking publish in thread pool
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(
                self._executor,
                self._publish_message,
                "email.send",
                message_data
            )

            if success:
                return {
                    "success": True,
                    "message_id": message_id,
                    "queued": True,
                    "recipient": to_email
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to queue email message",
                    "message_id": message_id
                }

        except Exception as e:
            logger.error(f"Error publishing email: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def publish_sms(
        self,
        tenant_id: str,
        to_phone: str,
        message: str,
        from_phone: Optional[str] = None,
        template_id: Optional[str] = None,
        template_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Publish SMS message to queue (async, non-blocking).

        Args:
            tenant_id: Tenant identifier
            to_phone: Recipient phone number
            message: SMS message content
            from_phone: Sender phone number (optional)
            template_id: SMS template ID (optional)
            template_data: Template variables (optional)

        Returns:
            Dict with success status and message_id
        """
        try:
            message_id = str(uuid.uuid4())

            message_data = {
                "message_id": message_id,
                "tenant_id": tenant_id,
                "to_phone": to_phone,
                "message": message,
                "from_phone": from_phone,
                "template_id": template_id,
                "template_data": template_data or {}
            }

            # Run blocking publish in thread pool
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(
                self._executor,
                self._publish_message,
                "sms.send",
                message_data
            )

            if success:
                return {
                    "success": True,
                    "message_id": message_id,
                    "queued": True,
                    "recipient": to_phone
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to queue SMS message",
                    "message_id": message_id
                }

        except Exception as e:
            logger.error(f"Error publishing SMS: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def close(self):
        """Close publisher and cleanup resources"""
        self._disconnect()
        self._executor.shutdown(wait=True)
        logger.info("RabbitMQ Publisher closed")


# Singleton instance
_publisher = RabbitMQPublisher()


def get_rabbitmq_publisher() -> RabbitMQPublisher:
    """Get singleton RabbitMQ publisher instance"""
    return _publisher
