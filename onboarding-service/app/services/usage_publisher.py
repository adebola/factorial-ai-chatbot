"""
RabbitMQ Publisher for Usage Events

Publishes usage events to the billing service when documents/websites are added or removed.
"""

import json
import os
import time
import threading
from datetime import datetime
from typing import Optional
from functools import wraps
import pika
from pika.exceptions import (
    AMQPConnectionError,
    AMQPChannelError,
    StreamLostError,
    ConnectionClosedByBroker
)

from ..core.logging_config import get_logger

logger = get_logger(__name__)


def _with_publish_retry(max_retries: int = 3, initial_delay: float = 0.5, backoff_factor: float = 2.0):
    """
    Decorator to add retry logic with exponential backoff to publish methods.

    Handles stale RabbitMQ connections by forcing fresh reconnection on each retry.
    Particularly useful for infrequent operations (like website removal) where
    connections may become stale over long periods (days).

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        initial_delay: Initial delay in seconds before first retry (default: 0.5)
        backoff_factor: Multiplier for delay on each retry (default: 2.0)

    Returns:
        Decorated function that returns bool (True on success, False on failure)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            method_name = func.__name__

            # Extract context for logging (tenant_id is first arg in all publish methods)
            tenant_id = kwargs.get('tenant_id', args[0] if args else 'unknown')

            for attempt in range(max_retries + 1):
                try:
                    # Force fresh reconnection on retry attempts (handles stale connections)
                    if attempt > 0:
                        logger.warning(
                            f"Retry attempt {attempt}/{max_retries} for {method_name}",
                            tenant_id=tenant_id,
                            method=method_name,
                            retry_attempt=attempt
                        )

                        # Attempt reconnection
                        reconnect_success = self._force_reconnection()

                        if not reconnect_success:
                            # Reconnection failed, continue to retry with exponential backoff
                            logger.warning(
                                f"Reconnection failed on attempt {attempt}, will retry",
                                tenant_id=tenant_id,
                                method=method_name
                            )
                            # Don't call the function if reconnection failed
                            # Just continue to next retry iteration
                            delay = initial_delay * (backoff_factor ** (attempt - 1))
                            time.sleep(delay)
                            continue

                        # Immediate validation after reconnection
                        if not self._is_connected():
                            logger.warning(
                                f"Channel not available after reconnection for {method_name}, will retry",
                                tenant_id=tenant_id,
                                method=method_name,
                                retry_attempt=attempt
                            )
                            delay = initial_delay * (backoff_factor ** (attempt - 1))
                            time.sleep(delay)
                            continue

                    # Call the original publish method
                    return func(self, *args, **kwargs)

                except (AttributeError, StreamLostError, ConnectionClosedByBroker,
                        AMQPConnectionError, AMQPChannelError) as e:
                    # Transient errors - retry with exponential backoff
                    error_type = type(e).__name__

                    if attempt < max_retries:
                        delay = initial_delay * (backoff_factor ** attempt)
                        logger.warning(
                            f"Transient error in {method_name}, retrying in {delay}s",
                            tenant_id=tenant_id,
                            method=method_name,
                            error_type=error_type,
                            error_message=str(e),
                            retry_attempt=attempt + 1,
                            retry_delay=delay
                        )
                        time.sleep(delay)
                    else:
                        # Max retries exhausted
                        logger.error(
                            f"Failed to publish after {max_retries} retries",
                            tenant_id=tenant_id,
                            method=method_name,
                            error_type=error_type,
                            error_message=str(e),
                            total_attempts=max_retries + 1
                        )
                        return False

                except Exception as e:
                    # Non-transient errors - fail fast without retry
                    logger.error(
                        f"Non-retryable error in {method_name}",
                        tenant_id=tenant_id,
                        method=method_name,
                        error_type=type(e).__name__,
                        error_message=str(e),
                        exc_info=True
                    )
                    return False

            # Should never reach here, but return False as safety
            return False

        return wrapper
    return decorator


class UsageEventPublisher:
    """
    Publisher for usage events to billing service.

    Publishes events when resources are added or removed:
    - usage.document.added
    - usage.document.removed
    - usage.website.added
    - usage.website.removed
    """

    def __init__(self):
        self.connection = None
        self.channel = None

        # Threading lock for connection management
        self._connection_lock = threading.RLock()

        # Get RabbitMQ config from environment
        self.rabbitmq_host = os.environ.get("RABBITMQ_HOST", "localhost")
        self.rabbitmq_port = int(os.environ.get("RABBITMQ_PORT", "5672"))
        self.rabbitmq_user = os.environ.get("RABBITMQ_USER", "guest")
        self.rabbitmq_password = os.environ.get("RABBITMQ_PASSWORD", "guest")
        self.rabbitmq_vhost = os.environ.get("RABBITMQ_VHOST", "/")

        # Usage exchange for billing service
        self.usage_exchange = os.environ.get("RABBITMQ_USAGE_EXCHANGE", "usage.events")

    def connect(self, max_retries: int = 3, retry_delay: int = 5):
        """
        Establish RabbitMQ connection with retry logic

        Args:
            max_retries: Maximum number of connection attempts (default: 3)
            retry_delay: Delay in seconds between retries (default: 5)
        """
        with self._connection_lock:
            import time

            # Force close any stale connections to prevent EOF errors
            if self.connection:
                try:
                    if not self.connection.is_closed and self.channel and self.channel.is_open:
                        # Connection and channel both exist and are open
                        # Verify channel is actually usable by testing exchange accessibility
                        try:
                            self.channel.exchange_declare(
                                exchange=self.usage_exchange,
                                exchange_type="topic",
                                durable=True,
                                passive=True  # Just check existence, don't create
                            )
                            logger.debug("Existing channel is valid and exchange is declared")
                            return  # Channel is confirmed valid
                        except Exception as e:
                            logger.warning(
                                f"Existing channel appears open but is not usable: {e}. "
                                "Will recreate channel."
                            )
                            # Fall through to recreate channel
                    # Connection exists but is closed, clean it up
                    self.connection.close()
                except Exception as e:
                    logger.warning(f"Error checking/closing stale connection: {e}")
                finally:
                    # Always reset connection objects when reconnecting
                    self.connection = None
                    self.channel = None

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

                    # Declare usage exchange (idempotent)
                    self.channel.exchange_declare(
                        exchange=self.usage_exchange,
                        exchange_type="topic",
                        durable=True
                    )

                    # Log successful connection
                    logger.info(
                        "✓ Successfully connected to RabbitMQ usage event publisher",
                        host=self.rabbitmq_host,
                        port=self.rabbitmq_port,
                        exchange=self.usage_exchange
                    )

                    # Verify and log connection state
                    if self._is_connected():
                        logger.info("✓ RabbitMQ connection verified: channel is open and ready")
                    else:
                        logger.error("✗ RabbitMQ connection verification FAILED: channel not available")

                    return

                except AMQPConnectionError as e:
                    retry_count += 1
                    self.connection = None
                    self.channel = None

                    error_msg = str(e) if str(e) else repr(e)

                    if retry_count >= max_retries:
                        logger.error(
                            f"Failed to connect usage publisher to RabbitMQ after {max_retries} attempts",
                            host=self.rabbitmq_host,
                            port=self.rabbitmq_port,
                            error=error_msg
                        )
                        raise

                    logger.warning(
                        f"Failed to connect usage publisher (attempt {retry_count}/{max_retries}): {error_msg}. "
                        f"Retrying in {retry_delay} seconds...",
                        host=self.rabbitmq_host,
                        port=self.rabbitmq_port
                    )
                    time.sleep(retry_delay)

                except Exception as e:
                    retry_count += 1
                    self.connection = None
                    self.channel = None

                    error_msg = str(e) if str(e) else repr(e)

                    if retry_count >= max_retries:
                        logger.error(
                            f"Unexpected error connecting usage publisher after {max_retries} attempts",
                            host=self.rabbitmq_host,
                            port=self.rabbitmq_port,
                            error=error_msg
                        )
                        raise

                    logger.warning(
                        f"Unexpected error connecting usage publisher (attempt {retry_count}/{max_retries}): {error_msg}. "
                        f"Retrying in {retry_delay} seconds...",
                        host=self.rabbitmq_host,
                        port=self.rabbitmq_port
                    )
                    time.sleep(retry_delay)

    def close(self):
        """Close RabbitMQ connection"""
        with self._connection_lock:
            if self.connection and self.connection.is_open:
                self.connection.close()
                logger.info("Closed RabbitMQ usage publisher connection")

    def _is_connected(self) -> bool:
        """
        Check if RabbitMQ connection and channel are valid and open.

        Returns:
            True if connection and channel are both open, False otherwise
        """
        try:
            return (
                self.connection is not None and
                not self.connection.is_closed and
                self.channel is not None and
                self.channel.is_open
            )
        except Exception as e:
            # If checking connection state throws, connection is invalid
            logger.debug(f"Error checking connection state: {e}")
            return False

    def _force_reconnection(self) -> bool:
        """
        Force a fresh RabbitMQ connection by closing existing connection and reconnecting.

        Returns:
            True if reconnection succeeded, False otherwise
        """
        with self._connection_lock:
            # Save old connection references
            old_connection = self.connection
            old_channel = self.channel

            # Reset to None to signal we're reconnecting
            self.connection = None
            self.channel = None

            try:
                # Attempt fresh connection (will reacquire lock, but RLock allows reentrant)
                self.connect()

                # Verify connection succeeded
                if not self._is_connected():
                    logger.error("Force reconnection failed: connection not valid after connect()")
                    return False

                # Additional test: verify exchange is accessible
                try:
                    self.channel.exchange_declare(
                        exchange=self.usage_exchange,
                        exchange_type="topic",
                        durable=True,
                        passive=True  # Just check existence
                    )
                except Exception as e:
                    logger.error(f"Force reconnection failed: channel exists but exchange is not accessible: {e}")
                    return False

                # Success - close old connection if it exists
                if old_connection:
                    try:
                        old_connection.close()
                    except Exception as e:
                        logger.debug(f"Error closing old connection: {e}")

                logger.info("Forced fresh RabbitMQ reconnection successful")
                return True

            except Exception as e:
                logger.error(f"Force reconnection failed with exception: {e}", exc_info=True)

            # Reconnection failed - restore old connection if it was still valid
            if old_connection and old_channel:
                try:
                    if not old_connection.is_closed and old_channel.is_open:
                        self.connection = old_connection
                        self.channel = old_channel
                        logger.warning("Restored previous connection after failed reconnection")
                except Exception:
                    pass

            return False

    @_with_publish_retry(max_retries=3, initial_delay=0.5)
    def publish_document_added(
        self,
        tenant_id: str,
        document_id: str,
        filename: str,
        file_size: int
    ) -> bool:
        """
        Publish usage.document.added event.

        Args:
            tenant_id: Tenant ID
            document_id: Document ID
            filename: Name of the document
            file_size: Size in bytes

        Returns:
            True if published successfully, False otherwise
        """
        # Ensure connection (connect() handles connection state internally)
        self.connect()

        # CRITICAL: Verify channel is valid before attempting publish
        if not self._is_connected():
            logger.error(
                f"Cannot publish document_added event: RabbitMQ channel is not available",
                tenant_id=tenant_id,
                document_id=document_id
            )
            # Raise exception to trigger retry mechanism
            raise AMQPConnectionError("Channel is None or closed")

        event = {
            "event_type": "usage.document.added",
            "tenant_id": tenant_id,
            "document_id": document_id,
            "filename": filename,
            "file_size": file_size,
            "count": 1,  # Incrementing by 1
            "timestamp": datetime.utcnow().isoformat()
        }

        self.channel.basic_publish(
            exchange=self.usage_exchange,
            routing_key="usage.document.added",
            body=json.dumps(event, default=str),
            properties=pika.BasicProperties(
                delivery_mode=2,  # Persistent
                content_type="application/json"
            )
        )

        logger.debug(
            "Published usage.document.added event",
            tenant_id=tenant_id,
            document_id=document_id,
            filename=filename
        )

        return True

    @_with_publish_retry(max_retries=3, initial_delay=0.5)
    def publish_document_removed(
        self,
        tenant_id: str,
        document_id: str,
        filename: str
    ) -> bool:
        """
        Publish usage.document.removed event.

        Args:
            tenant_id: Tenant ID
            document_id: Document ID
            filename: Name of the document

        Returns:
            True if published successfully, False otherwise
        """
        # Ensure connection (connect() handles connection state internally)
        self.connect()

        # CRITICAL: Verify channel is valid before attempting publish
        if not self._is_connected():
            logger.error(
                f"Cannot publish document_removed event: RabbitMQ channel is not available",
                tenant_id=tenant_id,
                document_id=document_id
            )
            # Raise exception to trigger retry mechanism
            raise AMQPConnectionError("Channel is None or closed")

        event = {
            "event_type": "usage.document.removed",
            "tenant_id": tenant_id,
            "document_id": document_id,
            "filename": filename,
            "count": -1,  # Decrementing by 1
            "timestamp": datetime.utcnow().isoformat()
        }

        self.channel.basic_publish(
            exchange=self.usage_exchange,
            routing_key="usage.document.removed",
            body=json.dumps(event, default=str),
            properties=pika.BasicProperties(
                delivery_mode=2,  # Persistent
                content_type="application/json"
            )
        )

        logger.debug(
            "Published usage.document.removed event",
            tenant_id=tenant_id,
            document_id=document_id,
            filename=filename
        )

        return True

    @_with_publish_retry(max_retries=3, initial_delay=0.5)
    def publish_website_added(
        self,
        tenant_id: str,
        website_id: str,
        url: str,
        pages_scraped: int
    ) -> bool:
        """
        Publish usage.website.added event.

        Args:
            tenant_id: Tenant ID
            website_id: Website ingestion ID
            url: Website URL
            pages_scraped: Number of pages scraped

        Returns:
            True if published successfully, False otherwise
        """
        # Ensure connection (connect() handles connection state internally)
        self.connect()

        # CRITICAL: Verify channel is valid before attempting publish
        if not self._is_connected():
            logger.error(
                f"Cannot publish website_added event: RabbitMQ channel is not available",
                tenant_id=tenant_id,
                website_id=website_id
            )
            # Raise exception to trigger retry mechanism
            raise AMQPConnectionError("Channel is None or closed")

        event = {
            "event_type": "usage.website.added",
            "tenant_id": tenant_id,
            "website_id": website_id,
            "url": url,
            "pages_scraped": pages_scraped,
            "count": 1,  # Incrementing by 1
            "timestamp": datetime.utcnow().isoformat()
        }

        self.channel.basic_publish(
            exchange=self.usage_exchange,
            routing_key="usage.website.added",
            body=json.dumps(event, default=str),
            properties=pika.BasicProperties(
                delivery_mode=2,  # Persistent
                content_type="application/json"
            )
        )

        logger.debug(
            "Published usage.website.added event",
            tenant_id=tenant_id,
            website_id=website_id,
            url=url,
            pages_scraped=pages_scraped
        )

        return True

    @_with_publish_retry(max_retries=3, initial_delay=0.5)
    def publish_website_removed(
        self,
        tenant_id: str,
        website_id: str,
        url: str
    ) -> bool:
        """
        Publish usage.website.removed event.

        Args:
            tenant_id: Tenant ID
            website_id: Website ingestion ID
            url: Website URL

        Returns:
            True if published successfully, False otherwise
        """
        # Ensure connection (connect() handles connection state internally)
        self.connect()

        # CRITICAL: Verify channel is valid before attempting publish
        if not self._is_connected():
            logger.error(
                f"Cannot publish website_removed event: RabbitMQ channel is not available",
                tenant_id=tenant_id,
                website_id=website_id
            )
            # Raise exception to trigger retry mechanism
            raise AMQPConnectionError("Channel is None or closed")

        event = {
            "event_type": "usage.website.removed",
            "tenant_id": tenant_id,
            "website_id": website_id,
            "url": url,
            "count": -1,  # Decrementing by 1
            "timestamp": datetime.utcnow().isoformat()
        }

        self.channel.basic_publish(
            exchange=self.usage_exchange,
            routing_key="usage.website.removed",
            body=json.dumps(event, default=str),
            properties=pika.BasicProperties(
                delivery_mode=2,  # Persistent
                content_type="application/json"
            )
        )

        logger.debug(
            "Published usage.website.removed event",
            tenant_id=tenant_id,
            website_id=website_id,
            url=url
        )

        return True


# Global usage event publisher instance
usage_publisher = UsageEventPublisher()
