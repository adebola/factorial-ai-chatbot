"""
RabbitMQ Event Publisher for Chat Messages

Publishes chat message events with quality metrics to the quality events exchange.
"""

import json
from datetime import datetime
from typing import Dict, Any, Optional
import pika
import os
from ..core.logging_config import get_logger

logger = get_logger(__name__)


class ChatEventPublisher:
    """
    Publisher for chat message events.

    Publishes to RabbitMQ exchange for consumption by answer-quality-service.
    """

    def __init__(self):
        self.connection = None
        self.channel = None
        self._is_connected = False

        # Get RabbitMQ config from environment
        self.rabbitmq_host = os.environ.get("RABBITMQ_HOST", "localhost")
        self.rabbitmq_port = int(os.environ.get("RABBITMQ_PORT", "5672"))
        self.rabbitmq_user = os.environ.get("RABBITMQ_USER", "guest")
        self.rabbitmq_password = os.environ.get("RABBITMQ_PASSWORD", "guest")
        self.rabbitmq_vhost = os.environ.get("RABBITMQ_VHOST", "/")

        # Two exchanges for different purposes
        self.chat_exchange = os.environ.get("RABBITMQ_CHAT_EXCHANGE", "chat.events")  # For quality analysis
        self.usage_exchange = os.environ.get("RABBITMQ_USAGE_EXCHANGE", "usage.events")  # For usage tracking

    def connect(self):
        """Establish RabbitMQ connection"""
        # Close existing connection if it exists but is not open
        if self.connection and not self.connection.is_open:
            try:
                self.connection.close()
            except:
                pass
            self.connection = None
            self.channel = None
            self._is_connected = False

        # Return if already connected
        if self._is_connected and self.connection and self.connection.is_open:
            return

        try:
            credentials = pika.PlainCredentials(
                self.rabbitmq_user,
                self.rabbitmq_password
            )
            parameters = pika.ConnectionParameters(
                host=self.rabbitmq_host,
                port=self.rabbitmq_port,
                virtual_host=self.rabbitmq_vhost,
                credentials=credentials,
                heartbeat=600,
                blocked_connection_timeout=300
            )

            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()

            # Declare both exchanges (idempotent)
            self.channel.exchange_declare(
                exchange=self.chat_exchange,
                exchange_type="topic",
                durable=True
            )
            self.channel.exchange_declare(
                exchange=self.usage_exchange,
                exchange_type="topic",
                durable=True
            )

            self._is_connected = True
            logger.info(
                f"Connected to RabbitMQ",
                host=self.rabbitmq_host,
                chat_exchange=self.chat_exchange,
                usage_exchange=self.usage_exchange
            )

        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}", exc_info=True)
            self._is_connected = False
            self.connection = None
            self.channel = None
            raise

    def close(self):
        """Close RabbitMQ connection"""
        if self.connection and self.connection.is_open:
            self.connection.close()
            self._is_connected = False
            logger.info("Closed RabbitMQ connection")

    def publish_message_created(
        self,
        tenant_id: str,
        session_id: str,
        message_id: str,
        message_type: str,
        content: str,
        quality_metrics: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Publish message.created event.

        Args:
            tenant_id: Tenant ID
            session_id: Chat session ID
            message_id: Message ID
            message_type: 'user' or 'assistant'
            content: Message content
            quality_metrics: Optional quality metrics (for assistant messages)

        Returns:
            True if published successfully, False otherwise
        """
        try:
            # Ensure connection
            if not self._is_connected:
                self.connect()

            # Build event payload
            event = {
                "event_type": "message.created",
                "tenant_id": tenant_id,
                "session_id": session_id,
                "message_id": message_id,
                "message_type": message_type,
                "content_preview": content[:200] if content else "",  # First 200 chars for sentiment
                "timestamp": datetime.now().isoformat()
            }

            # Add quality metrics for assistant messages
            if message_type == "assistant" and quality_metrics:
                event["quality_metrics"] = quality_metrics

            # Publish message.created event to chat exchange for quality analysis
            self.channel.basic_publish(
                exchange=self.chat_exchange,
                routing_key="message.created",
                body=json.dumps(event, default=str),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Persistent
                    content_type="application/json"
                )
            )

            logger.debug(
                f"Published message.created event to chat exchange",
                tenant_id=tenant_id,
                message_id=message_id,
                message_type=message_type,
                has_quality_metrics=quality_metrics is not None
            )

            return True

        except Exception as e:
            logger.error(
                f"Failed to publish message.created event: {e}",
                tenant_id=tenant_id,
                message_id=message_id,
                exc_info=True
            )
            # Attempt reconnection for next publish
            self._is_connected = False
            return False

    def publish_chat_usage_event(
        self,
        tenant_id: str,
        session_id: str,
        message_count: int = 1
    ) -> bool:
        """
        Publish usage.chat.message event to billing service.

        Args:
            tenant_id: Tenant ID
            session_id: Chat session ID
            message_count: Number of messages to increment (default 1)

        Returns:
            True if published successfully, False otherwise
        """
        try:
            # Ensure connection
            if not self._is_connected:
                self.connect()

            # Build event payload
            event = {
                "event_type": "usage.chat.message",
                "tenant_id": tenant_id,
                "session_id": session_id,
                "message_count": message_count,
                "timestamp": datetime.now().isoformat()
            }

            # Publish usage event to usage exchange for billing tracking
            self.channel.basic_publish(
                exchange=self.usage_exchange,
                routing_key="usage.chat.message",
                body=json.dumps(event, default=str),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Persistent
                    content_type="application/json"
                )
            )

            logger.debug(
                f"Published usage.chat.message event to usage exchange",
                tenant_id=tenant_id,
                session_id=session_id,
                message_count=message_count
            )

            return True

        except Exception as e:
            logger.error(
                f"Failed to publish usage.chat.message event: {e}",
                tenant_id=tenant_id,
                session_id=session_id,
                exc_info=True
            )
            # Attempt reconnection for next publish
            self._is_connected = False
            return False


# Global event publisher instance
event_publisher = ChatEventPublisher()
