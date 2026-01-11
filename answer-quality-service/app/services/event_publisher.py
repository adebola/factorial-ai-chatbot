"""
RabbitMQ Event Publisher

MIGRATED TO AIO-PIKA: Now uses async-native RabbitMQ operations with automatic reconnection.
Eliminated manual retry logic and connection state management.

Publishes quality-related events to RabbitMQ exchanges.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, Optional

from aio_pika import connect_robust, Message, ExchangeType, DeliveryMode
from aio_pika.abc import AbstractRobustConnection
from aio_pika.exceptions import AMQPException

from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class EventPublisher:
    """
    Async-native event publisher using aio-pika with automatic reconnection.

    Publishes quality-related events to RabbitMQ exchanges.
    """

    def __init__(self):
        self.connection: Optional[AbstractRobustConnection] = None
        logger.info("Event publisher initialized (aio-pika)")

    async def connect(self):
        """Establish robust connection with automatic reconnection."""
        if self.connection and not self.connection.is_closed:
            return

        self.connection = await connect_robust(
            host=settings.RABBITMQ_HOST,
            port=settings.RABBITMQ_PORT,
            login=settings.RABBITMQ_USER,
            password=settings.RABBITMQ_PASSWORD,
            virtualhost=settings.RABBITMQ_VHOST,
            reconnect_interval=1.0
        )

        logger.info(
            f"✓ Connected to RabbitMQ: {settings.RABBITMQ_HOST}:{settings.RABBITMQ_PORT}"
        )

    async def close(self):
        """Close RabbitMQ connection gracefully."""
        if self.connection and not self.connection.is_closed:
            await self.connection.close()
            logger.info("Closed RabbitMQ connection")

    async def _publish(self, routing_key: str, message: Dict[str, Any]) -> bool:
        """
        Internal method to publish a message.

        Args:
            routing_key: RabbitMQ routing key
            message: Message payload (will be JSON serialized)

        Returns:
            True if published successfully, False otherwise
        """
        try:
            await self.connect()

            async with self.connection.channel() as channel:
                exchange = await channel.declare_exchange(
                    settings.EXCHANGE_QUALITY_EVENTS,
                    ExchangeType.TOPIC,
                    durable=True
                )

                msg = Message(
                    body=json.dumps(message, default=str).encode(),
                    delivery_mode=DeliveryMode.PERSISTENT,
                    content_type="application/json"
                )

                await exchange.publish(msg, routing_key=routing_key)

            logger.debug(
                f"Published event: {routing_key}",
                event_type=message.get("event_type")
            )

            return True

        except Exception as e:
            logger.error(f"Failed to publish event {routing_key}: {e}", exc_info=True)
            return False

    async def publish_feedback_submitted(
        self,
        tenant_id: str,
        session_id: str,
        message_id: str,
        feedback_type: str,
        has_comment: bool
    ) -> bool:
        """
        Publish feedback submitted event.

        Event: feedback.submitted

        Args:
            tenant_id: Tenant ID
            session_id: Chat session ID
            message_id: Message ID that received feedback
            feedback_type: 'helpful' or 'not_helpful'
            has_comment: Whether user provided a comment

        Returns:
            True if published successfully, False otherwise
        """
        event = {
            "event_type": "feedback.submitted",
            "tenant_id": tenant_id,
            "session_id": session_id,
            "message_id": message_id,
            "feedback_type": feedback_type,
            "has_comment": has_comment,
            "timestamp": datetime.now().isoformat()
        }

        result = await self._publish("feedback.submitted", event)

        if result:
            logger.info(
                "Published feedback.submitted event",
                tenant_id=tenant_id,
                message_id=message_id,
                feedback_type=feedback_type
            )

        return result

    async def publish_knowledge_gap_detected(
        self,
        tenant_id: str,
        gap_id: str,
        pattern: str,
        occurrence_count: int,
        avg_confidence: float,
        example_questions: list
    ) -> bool:
        """
        Publish knowledge gap detected event.

        Event: knowledge.gap.detected

        Args:
            tenant_id: Tenant ID
            gap_id: Knowledge gap ID
            pattern: Question pattern
            occurrence_count: How many times this gap has occurred
            avg_confidence: Average confidence of answers
            example_questions: Example questions showing the gap

        Returns:
            True if published successfully, False otherwise
        """
        event = {
            "event_type": "knowledge.gap.detected",
            "tenant_id": tenant_id,
            "gap_id": gap_id,
            "pattern": pattern,
            "occurrence_count": occurrence_count,
            "avg_confidence": avg_confidence,
            "example_questions": example_questions[:3],  # Limit to 3 examples
            "timestamp": datetime.now().isoformat()
        }

        result = await self._publish("knowledge.gap.detected", event)

        if result:
            logger.info(
                "Published knowledge.gap.detected event",
                tenant_id=tenant_id,
                gap_id=gap_id,
                pattern=pattern,
                occurrence_count=occurrence_count
            )

        return result

    async def publish_session_quality_updated(
        self,
        tenant_id: str,
        session_id: str,
        session_success: bool,
        helpful_count: int,
        not_helpful_count: int
    ) -> bool:
        """
        Publish session quality updated event.

        Event: session.quality.updated

        Args:
            tenant_id: Tenant ID
            session_id: Chat session ID
            session_success: Whether session was successful
            helpful_count: Number of helpful feedback
            not_helpful_count: Number of not helpful feedback

        Returns:
            True if published successfully, False otherwise
        """
        event = {
            "event_type": "session.quality.updated",
            "tenant_id": tenant_id,
            "session_id": session_id,
            "session_success": session_success,
            "helpful_count": helpful_count,
            "not_helpful_count": not_helpful_count,
            "timestamp": datetime.now().isoformat()
        }

        result = await self._publish("session.quality.updated", event)

        if result:
            logger.info(
                "Published session.quality.updated event",
                tenant_id=tenant_id,
                session_id=session_id,
                session_success=session_success
            )

        return result


# Global publisher instance
event_publisher = EventPublisher()
