"""
RabbitMQ Event Publisher for Chat Messages

MIGRATED TO AIO-PIKA: Now uses async-native RabbitMQ operations with automatic reconnection.
Eliminated manual retry logic, connection state management, and thread-safety concerns.

Publishes chat message events with quality metrics to the quality events exchange.
"""

import json
import uuid
import os
from datetime import datetime
from typing import Dict, Any, Optional

from aio_pika import connect_robust, Message, ExchangeType, DeliveryMode
from aio_pika.abc import AbstractRobustConnection
from aio_pika.exceptions import AMQPException

from ..core.logging_config import get_logger

logger = get_logger(__name__)


class ChatEventPublisher:
    """
    Async-native publisher for chat message events using aio-pika with automatic reconnection.

    Publishes to two exchanges:
    - chat.events: For consumption by answer-quality-service (quality analysis)
    - usage.events: For consumption by billing-service (usage tracking)
    """

    def __init__(self):
        self.connection: Optional[AbstractRobustConnection] = None

        # Get RabbitMQ config from environment
        self.rabbitmq_host = os.environ.get("RABBITMQ_HOST", "localhost")
        self.rabbitmq_port = int(os.environ.get("RABBITMQ_PORT", "5672"))
        self.rabbitmq_user = os.environ.get("RABBITMQ_USER", "guest")
        self.rabbitmq_password = os.environ.get("RABBITMQ_PASSWORD", "guest")
        self.rabbitmq_vhost = os.environ.get("RABBITMQ_VHOST", "/")

        # Two exchanges for different purposes
        self.chat_exchange = os.environ.get("RABBITMQ_CHAT_EXCHANGE", "chat.events")  # For quality analysis
        self.usage_exchange = os.environ.get("RABBITMQ_USAGE_EXCHANGE", "usage.events")  # For usage tracking

        logger.info("Chat event publisher initialized (aio-pika)")

    async def connect(self):
        """Establish robust connection with automatic reconnection."""
        if self.connection and not self.connection.is_closed:
            return

        self.connection = await connect_robust(
            host=self.rabbitmq_host,
            port=self.rabbitmq_port,
            login=self.rabbitmq_user,
            password=self.rabbitmq_password,
            virtualhost=self.rabbitmq_vhost,
            reconnect_interval=1.0
        )

        logger.info(
            "✓ Successfully connected to RabbitMQ event publisher",
            host=self.rabbitmq_host,
            port=self.rabbitmq_port,
            vhost=self.rabbitmq_vhost,
            chat_exchange=self.chat_exchange,
            usage_exchange=self.usage_exchange
        )

    async def close(self):
        """Close RabbitMQ connection gracefully."""
        if self.connection and not self.connection.is_closed:
            await self.connection.close()
            logger.info("Closed RabbitMQ chat event publisher connection")

    async def publish_message_created(
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
            await self.connect()

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

            async with self.connection.channel() as channel:
                exchange = await channel.declare_exchange(
                    self.chat_exchange,
                    ExchangeType.TOPIC,
                    durable=True
                )

                message = Message(
                    body=json.dumps(event, default=str).encode(),
                    delivery_mode=DeliveryMode.PERSISTENT,
                    content_type="application/json"
                )

                await exchange.publish(message, routing_key="message.created")

            logger.debug(
                "Published message.created event to chat exchange",
                tenant_id=tenant_id,
                message_id=message_id,
                message_type=message_type,
                has_quality_metrics=quality_metrics is not None
            )

            return True

        except Exception as e:
            logger.exception(
                f"Failed to publish message.created event: {e}",
                tenant_id=tenant_id,
                message_id=message_id)
            return False

    async def publish_chat_usage_event(
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
            await self.connect()

            # Build event payload
            event = {
                "event_id": str(uuid.uuid4()),
                "event_type": "usage.chat.message",
                "tenant_id": tenant_id,
                "session_id": session_id,
                "message_count": message_count,
                "timestamp": datetime.now().isoformat()
            }

            async with self.connection.channel() as channel:
                exchange = await channel.declare_exchange(
                    self.usage_exchange,
                    ExchangeType.TOPIC,
                    durable=True
                )

                message = Message(
                    body=json.dumps(event, default=str).encode(),
                    delivery_mode=DeliveryMode.PERSISTENT,
                    content_type="application/json"
                )

                await exchange.publish(message, routing_key="usage.chat.message")

            logger.info(
                "Published usage.chat.message event to usage exchange",
                tenant_id=tenant_id,
                session_id=session_id,
                message_count=message_count
            )

            return True

        except Exception as e:
            logger.exception(
                f"Failed to publish usage.chat.message event: {e}",
                tenant_id=tenant_id,
                session_id=session_id)
            return False


# Global event publisher instance
event_publisher = ChatEventPublisher()