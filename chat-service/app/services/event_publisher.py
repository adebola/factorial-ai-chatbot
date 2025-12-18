"""
RabbitMQ Event Publisher for Chat Messages

Publishes chat message events with quality metrics to the quality events exchange.
"""

import json
import time
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
import pika
import os
from pika.exceptions import AMQPConnectionError, StreamLostError, ConnectionClosedByBroker
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

    def connect(self, max_retries: int = 3, retry_delay: int = 5):
        """
        Establish RabbitMQ connection with retry logic

        Args:
            max_retries: Maximum number of connection attempts (default: 3)
            retry_delay: Delay in seconds between retries (default: 5)
        """
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

        retry_count = 0
        while retry_count < max_retries:
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

                # Log successful connection with full details
                connection_success = {
                    "host": self.rabbitmq_host,
                    "port": self.rabbitmq_port,
                    "vhost": self.rabbitmq_vhost,
                    "user": self.rabbitmq_user,
                    "chat_exchange": self.chat_exchange,
                    "usage_exchange": self.usage_exchange,
                    "retry_attempt": retry_count + 1 if retry_count > 0 else 1
                }

                logger.info(
                    "✓ Successfully connected to RabbitMQ event publisher",
                    extra=connection_success
                )

                # Success - exit retry loop
                return

            except AMQPConnectionError as e:
                retry_count += 1
                self._is_connected = False
                self.connection = None
                self.channel = None

                error_msg = str(e) if str(e) else repr(e)

                # Log connection details for debugging
                connection_details = {
                    "host": self.rabbitmq_host,
                    "port": self.rabbitmq_port,
                    "vhost": self.rabbitmq_vhost,
                    "user": self.rabbitmq_user,
                    "error": error_msg,
                    "error_type": type(e).__name__
                }

                if retry_count >= max_retries:
                    logger.error(
                        f"Failed to connect event publisher to RabbitMQ after {max_retries} attempts",
                        extra=connection_details,
                        exc_info=True
                    )
                    raise

                logger.warning(
                    f"Failed to connect event publisher to RabbitMQ (attempt {retry_count}/{max_retries}): {error_msg}. "
                    f"Retrying in {retry_delay} seconds...",
                    extra=connection_details
                )
                time.sleep(retry_delay)

            except Exception as e:
                retry_count += 1
                self._is_connected = False
                self.connection = None
                self.channel = None

                error_msg = str(e) if str(e) else repr(e)

                # Log connection details for debugging
                connection_details = {
                    "host": self.rabbitmq_host,
                    "port": self.rabbitmq_port,
                    "vhost": self.rabbitmq_vhost,
                    "user": self.rabbitmq_user,
                    "error": error_msg,
                    "error_type": type(e).__name__
                }

                if retry_count >= max_retries:
                    logger.error(
                        f"Unexpected error connecting event publisher to RabbitMQ after {max_retries} attempts",
                        extra=connection_details,
                        exc_info=True
                    )
                    raise

                logger.warning(
                    f"Unexpected error connecting event publisher (attempt {retry_count}/{max_retries}): {error_msg}. "
                    f"Retrying in {retry_delay} seconds...",
                    extra=connection_details,
                    exc_info=True
                )
                time.sleep(retry_delay)

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

        except (StreamLostError, ConnectionClosedByBroker) as e:
            # Connection lost during publish - attempt immediate reconnection and retry
            logger.warning(
                f"RabbitMQ connection lost during publish: {e}. Attempting reconnection...",
                tenant_id=tenant_id,
                message_id=message_id,
                error_type=type(e).__name__
            )
            self._is_connected = False
            self.connection = None
            self.channel = None

            try:
                # Attempt reconnection
                self.connect()

                # Retry publish once after reconnection
                self.channel.basic_publish(
                    exchange=self.chat_exchange,
                    routing_key="message.created",
                    body=json.dumps(event, default=str),
                    properties=pika.BasicProperties(
                        delivery_mode=2,  # Persistent
                        content_type="application/json"
                    )
                )

                logger.info(
                    "Successfully republished message.created event after reconnection",
                    tenant_id=tenant_id,
                    message_id=message_id
                )
                return True

            except Exception as retry_error:
                logger.error(
                    f"Failed to republish message.created event after reconnection: {retry_error}",
                    tenant_id=tenant_id,
                    message_id=message_id,
                    exc_info=True
                )
                return False

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
                "event_id": str(uuid.uuid4()),
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

            logger.info(
                f"Published usage.chat.message event to usage exchange",
                tenant_id=tenant_id,
                session_id=session_id,
                message_count=message_count
            )

            return True

        except (StreamLostError, ConnectionClosedByBroker) as e:
            # Connection lost during publish - attempt immediate reconnection and retry
            logger.warning(
                f"RabbitMQ connection lost during usage event publish: {e}. Attempting reconnection...",
                tenant_id=tenant_id,
                session_id=session_id,
                error_type=type(e).__name__
            )
            self._is_connected = False
            self.connection = None
            self.channel = None

            try:
                # Attempt reconnection
                self.connect()

                # Retry publish once after reconnection
                self.channel.basic_publish(
                    exchange=self.usage_exchange,
                    routing_key="usage.chat.message",
                    body=json.dumps(event, default=str),
                    properties=pika.BasicProperties(
                        delivery_mode=2,  # Persistent
                        content_type="application/json"
                    )
                )

                logger.info(
                    "Successfully republished usage.chat.message event after reconnection",
                    tenant_id=tenant_id,
                    session_id=session_id
                )
                return True

            except Exception as retry_error:
                logger.error(
                    f"Failed to republish usage.chat.message event after reconnection: {retry_error}",
                    tenant_id=tenant_id,
                    session_id=session_id,
                    exc_info=True
                )
                return False

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
