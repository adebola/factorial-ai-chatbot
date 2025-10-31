"""
RabbitMQ Consumer

Consumes chat.message.created events from the chat service
and processes them for quality analysis.
"""

import json
import pika
import threading
from typing import Callable
from app.core.config import settings
from app.core.logging_config import get_logger
from app.core.database import SessionLocal
from app.services.quality_analyzer import QualityAnalyzer
from app.schemas.quality import ChatMessageEvent

logger = get_logger(__name__)


class RabbitMQConsumer:
    """
    Consumer for chat message events.

    Listens to chat.message.created events and processes quality metrics.
    """

    def __init__(self):
        self.connection = None
        self.channel = None
        self.consuming = False
        self._consumer_thread = None

    def connect(self):
        """Establish RabbitMQ connection"""
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

            # Declare exchange (idempotent)
            self.channel.exchange_declare(
                exchange=settings.EXCHANGE_CHAT_EVENTS,
                exchange_type="topic",
                durable=True
            )

            # Declare queue
            self.channel.queue_declare(
                queue=settings.QUEUE_CHAT_MESSAGES,
                durable=True
            )

            # Bind queue to exchange with routing key
            self.channel.queue_bind(
                exchange=settings.EXCHANGE_CHAT_EVENTS,
                queue=settings.QUEUE_CHAT_MESSAGES,
                routing_key="message.created"
            )

            logger.info(
                f"Connected to RabbitMQ and bound queue",
                queue=settings.QUEUE_CHAT_MESSAGES,
                exchange=settings.EXCHANGE_CHAT_EVENTS,
                routing_key="message.created"
            )

        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}", exc_info=True)
            raise

    def start_consuming(self):
        """
        Start consuming messages in a separate thread.

        This allows the FastAPI application to continue running
        while the consumer processes messages in the background.
        """
        if self.consuming:
            logger.warning("Consumer is already running")
            return

        self._consumer_thread = threading.Thread(
            target=self._consume_loop,
            daemon=True  # Thread will exit when main program exits
        )
        self._consumer_thread.start()
        logger.info("Started RabbitMQ consumer thread")

    def _consume_loop(self):
        """Internal consume loop (runs in separate thread)"""
        try:
            if not self.connection or self.connection.is_closed:
                self.connect()

            self.channel.basic_qos(prefetch_count=1)
            self.channel.basic_consume(
                queue=settings.QUEUE_CHAT_MESSAGES,
                on_message_callback=self._on_message,
                auto_ack=False  # Manual acknowledgment for reliability
            )

            self.consuming = True
            logger.info(
                "RabbitMQ consumer started",
                queue=settings.QUEUE_CHAT_MESSAGES
            )

            self.channel.start_consuming()

        except Exception as e:
            logger.error(f"Consumer loop error: {e}", exc_info=True)
            self.consuming = False

    def _on_message(self, channel, method, properties, body):
        """
        Handle incoming message.

        Args:
            channel: RabbitMQ channel
            method: Delivery method
            properties: Message properties
            body: Message body (JSON)
        """
        try:
            # Parse message
            event_data = json.loads(body)
            event = ChatMessageEvent(**event_data)

            logger.info(
                "Received chat message event",
                event_type=event.event_type,
                tenant_id=event.tenant_id,
                message_id=event.message_id,
                message_type=event.message_type
            )

            # Only process assistant messages (AI responses)
            if event.message_type == "assistant":
                self._process_message(event)
            else:
                logger.debug(
                    "Skipping user message (only processing assistant messages)",
                    message_id=event.message_id
                )

            # Acknowledge message
            channel.basic_ack(delivery_tag=method.delivery_tag)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse message JSON: {e}", exc_info=True)
            # Reject and don't requeue (malformed message)
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            # Reject and requeue for retry
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

    def _process_message(self, event: ChatMessageEvent):
        """
        Process a chat message event.

        Args:
            event: Parsed chat message event
        """
        # Create database session
        db = SessionLocal()

        try:
            # Extract quality metrics from event
            metrics = event.quality_metrics or {}

            # Create quality analyzer
            analyzer = QualityAnalyzer(db)

            # Analyze and store quality metrics
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            quality_record = loop.run_until_complete(
                analyzer.analyze_message_quality(
                    tenant_id=event.tenant_id,
                    message_id=event.message_id,
                    session_id=event.session_id,
                    metrics=metrics,
                    content=event.content_preview  # For sentiment analysis
                )
            )

            logger.info(
                "Successfully processed message quality",
                tenant_id=event.tenant_id,
                message_id=event.message_id,
                confidence=quality_record.answer_confidence,
                sentiment=quality_record.basic_sentiment
            )

        except Exception as e:
            logger.error(
                f"Failed to process message quality: {e}",
                tenant_id=event.tenant_id,
                message_id=event.message_id,
                exc_info=True
            )
            raise  # Re-raise to trigger requeue

        finally:
            db.close()

    def stop_consuming(self):
        """Stop consuming messages"""
        if self.channel and self.channel.is_open:
            self.channel.stop_consuming()

        self.consuming = False
        logger.info("Stopped RabbitMQ consumer")

    def close(self):
        """Close RabbitMQ connection"""
        self.stop_consuming()

        if self.connection and self.connection.is_open:
            self.connection.close()
            logger.info("Closed RabbitMQ connection")


# Global consumer instance
rabbitmq_consumer = RabbitMQConsumer()
