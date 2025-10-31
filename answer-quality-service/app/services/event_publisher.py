"""
RabbitMQ Event Publisher

Publishes quality-related events to RabbitMQ exchanges.
"""

import json
from datetime import datetime
from typing import Any, Dict
import pika
from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class EventPublisher:
    """
    Publish quality-related events to RabbitMQ.

    Uses lazy connection (connects on first publish).
    """

    def __init__(self):
        self.connection = None
        self.channel = None
        self._is_connected = False

    def connect(self):
        """Establish RabbitMQ connection"""
        if self._is_connected and self.connection and self.connection.is_open:
            return

        try:
            credentials = pika.PlainCredentials(
                settings.RABBITMQ_USER,
                settings.RABBITMQ_PASSWORD
            )
            parameters = pika.ConnectionParameters(
                host=settings.RABBITMQ_HOST,
                port=settings.RABBITMQ_PORT,
                virtual_host=settings.RABBITMQ_VHOST,
                credentials=credentials,
                heartbeat=600,
                blocked_connection_timeout=300
            )

            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()

            # Declare quality events exchange
            self.channel.exchange_declare(
                exchange=settings.EXCHANGE_QUALITY_EVENTS,
                exchange_type="topic",
                durable=True
            )

            self._is_connected = True
            logger.info(f"Connected to RabbitMQ: {settings.RABBITMQ_HOST}:{settings.RABBITMQ_PORT}")

        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            self._is_connected = False
            raise

    def close(self):
        """Close RabbitMQ connection"""
        if self.connection and self.connection.is_open:
            self.connection.close()
            self._is_connected = False
            logger.info("Closed RabbitMQ connection")

    def _publish(self, routing_key: str, message: Dict[str, Any]):
        """
        Internal method to publish a message.

        Args:
            routing_key: RabbitMQ routing key
            message: Message payload (will be JSON serialized)
        """
        # Ensure connection
        if not self._is_connected:
            self.connect()

        try:
            self.channel.basic_publish(
                exchange=settings.EXCHANGE_QUALITY_EVENTS,
                routing_key=routing_key,
                body=json.dumps(message, default=str),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Persistent
                    content_type="application/json"
                )
            )

            logger.debug(f"Published event: {routing_key}", event_type=message.get("event_type"))

        except Exception as e:
            logger.error(f"Failed to publish event {routing_key}: {e}")
            # Attempt reconnection
            self._is_connected = False
            raise

    def publish_feedback_submitted(
        self,
        tenant_id: str,
        session_id: str,
        message_id: str,
        feedback_type: str,
        has_comment: bool
    ):
        """
        Publish feedback submitted event.

        Event: feedback.submitted

        Args:
            tenant_id: Tenant ID
            session_id: Chat session ID
            message_id: Message ID that received feedback
            feedback_type: 'helpful' or 'not_helpful'
            has_comment: Whether user provided a comment
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

        self._publish("feedback.submitted", event)

        logger.info(
            "Published feedback.submitted event",
            tenant_id=tenant_id,
            message_id=message_id,
            feedback_type=feedback_type
        )

    def publish_knowledge_gap_detected(
        self,
        tenant_id: str,
        gap_id: str,
        pattern: str,
        occurrence_count: int,
        avg_confidence: float,
        example_questions: list
    ):
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

        self._publish("knowledge.gap.detected", event)

        logger.info(
            "Published knowledge.gap.detected event",
            tenant_id=tenant_id,
            gap_id=gap_id,
            pattern=pattern,
            occurrence_count=occurrence_count
        )

    def publish_session_quality_updated(
        self,
        tenant_id: str,
        session_id: str,
        session_success: bool,
        helpful_count: int,
        not_helpful_count: int
    ):
        """
        Publish session quality updated event.

        Event: session.quality.updated

        Args:
            tenant_id: Tenant ID
            session_id: Chat session ID
            session_success: Whether session was successful
            helpful_count: Number of helpful feedback
            not_helpful_count: Number of not helpful feedback
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

        self._publish("session.quality.updated", event)

        logger.info(
            "Published session.quality.updated event",
            tenant_id=tenant_id,
            session_id=session_id,
            session_success=session_success
        )


# Global publisher instance
event_publisher = EventPublisher()
