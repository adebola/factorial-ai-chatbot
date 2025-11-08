"""
RabbitMQ Limit Warning Consumer

Listens for limit warning messages from the billing service and invalidates
the local Redis cache to force fresh limit checks.
"""

import json
import os
import sys
import threading
import time
from typing import Dict, Any

import pika
from pika.exceptions import AMQPConnectionError

from .usage_cache import usage_cache
from ..core.logging_config import get_logger

logger = get_logger(__name__)


class LimitWarningConsumer:
    """
    Consumer for limit warning events from billing service.

    Listens for:
    - usage.limit.warning - When a tenant approaches/exceeds limits
    - usage.limit.exceeded - When a tenant hard-exceeds limits

    Actions:
    - Invalidates Redis cache for the tenant
    - Forces next check to fetch fresh data from billing service
    """

    def __init__(self):
        self.connection = None
        self.channel = None
        self.consumer_thread = None
        self._is_running = False

        # Get RabbitMQ config from environment
        self.rabbitmq_host = os.environ.get("RABBITMQ_HOST", "localhost")
        self.rabbitmq_port = int(os.environ.get("RABBITMQ_PORT", "5672"))
        self.rabbitmq_user = os.environ.get("RABBITMQ_USER", "guest")
        self.rabbitmq_password = os.environ.get("RABBITMQ_PASSWORD", "guest")
        self.rabbitmq_vhost = os.environ.get("RABBITMQ_VHOST", "/")

        # Exchange and queue configuration
        self.exchange = os.environ.get("RABBITMQ_USAGE_EXCHANGE", "usage.events")
        self.queue_name = "chat-service.limit-warnings"

    def connect(self):
        """Establish RabbitMQ connection and declare queue (single attempt - retries handled by caller)"""
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

        # Declare exchange (idempotent)
        self.channel.exchange_declare(
            exchange=self.exchange,
            exchange_type='topic',
            durable=True
        )

        # Declare queue
        self.channel.queue_declare(
            queue=self.queue_name,
            durable=True
        )

        # Bind queue to exchange with routing keys
        self.channel.queue_bind(
            queue=self.queue_name,
            exchange=self.exchange,
            routing_key="usage.limit.warning"
        )

        self.channel.queue_bind(
            queue=self.queue_name,
            exchange=self.exchange,
            routing_key="usage.limit.exceeded"
        )

        # Log successful connection with full details
        connection_success = {
            "host": self.rabbitmq_host,
            "port": self.rabbitmq_port,
            "vhost": self.rabbitmq_vhost,
            "user": self.rabbitmq_user,
            "exchange": self.exchange,
            "queue": self.queue_name
        }

        logger.info(
            "✓ Successfully connected to RabbitMQ for limit warning consumption",
            extra=connection_success
        )

    def _handle_limit_warning(self, ch, method, properties, body):
        """
        Handle incoming limit warning message.

        Args:
            ch: Channel
            method: Method
            properties: Properties
            body: Message body (JSON)
        """
        try:
            # Parse event
            event = json.loads(body)

            tenant_id = event.get("tenant_id")
            usage_type = event.get("usage_type")
            routing_key = method.routing_key

            logger.info(
                f"Received limit warning",
                extra={
                    "tenant_id": tenant_id,
                    "usage_type": usage_type,
                    "routing_key": routing_key
                }
            )

            # Invalidate cache for this tenant
            if tenant_id:
                usage_cache.invalidate_cache(tenant_id)
                logger.info(
                    f"Cache invalidated for tenant {tenant_id} due to limit warning"
                )

            # Acknowledge message
            ch.basic_ack(delivery_tag=method.delivery_tag)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse limit warning message: {e}")
            # Reject malformed message (don't requeue)
            ch.basic_reject(delivery_tag=method.delivery_tag, requeue=False)

        except Exception as e:
            logger.error(f"Error handling limit warning: {e}", exc_info=True)
            # Acknowledge to prevent redelivery loop
            ch.basic_ack(delivery_tag=method.delivery_tag)

    def start(self):
        """Start consuming limit warnings in a background thread with connection retries"""
        if self._is_running:
            logger.warning("Limit warning consumer already running")
            return

        # Start consuming in background thread (retries handled inside thread)
        def consume_with_retry():
            """Consumer loop with built-in connection retry logic"""
            logger.info("Limit warning consumer background thread started")
            retry_count = 0
            max_retries = 3
            retry_delay = 5  # seconds

            while retry_count < max_retries:
                try:
                    # Connect to RabbitMQ
                    logger.info("Attempting to connect to RabbitMQ for limit warning consumer...")
                    self.connect()

                    # Connection successful - reset retry count
                    retry_count = 0

                    # Set up consumer
                    self.channel.basic_qos(prefetch_count=10)
                    self.channel.basic_consume(
                        queue=self.queue_name,
                        on_message_callback=self._handle_limit_warning,
                        auto_ack=False
                    )

                    self._is_running = True

                    # Log successful consumer start with details
                    consumer_info = {
                        "host": self.rabbitmq_host,
                        "port": self.rabbitmq_port,
                        "exchange": self.exchange,
                        "queue": self.queue_name,
                        "routing_keys": ["usage.limit.warning", "usage.limit.exceeded"]
                    }

                    logger.info(
                        "✓ Limit warning consumer started successfully - listening for events",
                        extra=consumer_info
                    )
                    sys.stdout.flush()  # Force flush logs in Docker

                    # Start consuming (blocks until stopped or connection error)
                    self.channel.start_consuming()

                except AMQPConnectionError as e:
                    retry_count += 1
                    self._is_running = False

                    error_msg = str(e) if str(e) else repr(e)

                    # Log connection details for debugging
                    connection_details = {
                        "host": self.rabbitmq_host,
                        "port": self.rabbitmq_port,
                        "vhost": self.rabbitmq_vhost,
                        "user": self.rabbitmq_user,
                        "exchange": self.exchange,
                        "queue": self.queue_name,
                        "error": error_msg,
                        "error_type": type(e).__name__
                    }

                    if retry_count >= max_retries:
                        logger.error(
                            f"Failed to connect to RabbitMQ after {max_retries} attempts. "
                            f"Limit warning consumer will not start.",
                            extra=connection_details,
                            exc_info=True
                        )
                        sys.stdout.flush()  # Force flush logs in Docker
                        return

                    logger.warning(
                        f"Failed to connect to RabbitMQ (attempt {retry_count}/{max_retries}): {error_msg}. "
                        f"Retrying in {retry_delay} seconds...",
                        extra=connection_details
                    )
                    sys.stdout.flush()  # Force flush logs in Docker
                    time.sleep(retry_delay)

                except Exception as e:
                    retry_count += 1
                    self._is_running = False

                    error_msg = str(e) if str(e) else repr(e)

                    # Log connection details for debugging
                    connection_details = {
                        "host": self.rabbitmq_host,
                        "port": self.rabbitmq_port,
                        "vhost": self.rabbitmq_vhost,
                        "user": self.rabbitmq_user,
                        "exchange": self.exchange,
                        "queue": self.queue_name,
                        "error": error_msg,
                        "error_type": type(e).__name__
                    }

                    if retry_count >= max_retries:
                        logger.error(
                            f"Unexpected error in limit warning consumer after {max_retries} attempts. "
                            f"Consumer will not start.",
                            extra=connection_details,
                            exc_info=True
                        )
                        sys.stdout.flush()  # Force flush logs in Docker
                        return

                    logger.warning(
                        f"Error in consumer thread (attempt {retry_count}/{max_retries}): {error_msg}. "
                        f"Retrying in {retry_delay} seconds...",
                        extra=connection_details,
                        exc_info=True
                    )
                    sys.stdout.flush()  # Force flush logs in Docker
                    time.sleep(retry_delay)

                finally:
                    # Clean up connection if it exists
                    if self.connection and not self.connection.is_closed:
                        try:
                            self.connection.close()
                        except Exception:
                            pass

            # If we exit the loop, all retries failed
            logger.warning(
                "Limit warning consumer stopped after exhausting all retries. "
                "Service will continue without limit warning functionality."
            )
            self._is_running = False

        self.consumer_thread = threading.Thread(target=consume_with_retry, daemon=True)
        self.consumer_thread.start()

        logger.info("Limit warning consumer thread started")

    def stop(self):
        """Stop consuming limit warnings"""
        if not self._is_running:
            return

        try:
            logger.info("Stopping limit warning consumer")
            self._is_running = False

            if self.channel and self.channel.is_open:
                self.channel.stop_consuming()

            if self.connection and self.connection.is_open:
                self.connection.close()

            if self.consumer_thread and self.consumer_thread.is_alive():
                self.consumer_thread.join(timeout=5)

            logger.info("Limit warning consumer stopped")

        except Exception as e:
            logger.error(f"Error stopping limit warning consumer: {e}", exc_info=True)


# Global consumer instance
limit_warning_consumer = LimitWarningConsumer()
