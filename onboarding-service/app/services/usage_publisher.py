"""
RabbitMQ Publisher for Usage Events

Publishes usage events to the billing service when documents/websites are added or removed.
"""

import json
import os
from datetime import datetime
from typing import Optional
import pika
from pika.exceptions import AMQPConnectionError

from ..core.logging_config import get_logger

logger = get_logger(__name__)


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
        import time

        # Force close any stale connections to prevent EOF errors
        if self.connection:
            try:
                if not self.connection.is_closed:
                    # Connection exists and is open
                    return
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
        if self.connection and self.connection.is_open:
            self.connection.close()
            logger.info("Closed RabbitMQ usage publisher connection")

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
        try:
            # Ensure connection (connect() handles connection state internally)
            self.connect()

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

        except Exception as e:
            logger.error(
                f"Failed to publish usage.document.added event: {e}",
                tenant_id=tenant_id,
                document_id=document_id,
                exc_info=True
            )
            return False

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
        try:
            # Ensure connection (connect() handles connection state internally)
            self.connect()

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

        except Exception as e:
            logger.error(
                f"Failed to publish usage.document.removed event: {e}",
                tenant_id=tenant_id,
                document_id=document_id,
                exc_info=True
            )
            return False

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
        try:
            # Ensure connection (connect() handles connection state internally)
            self.connect()

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

        except Exception as e:
            logger.error(
                f"Failed to publish usage.website.added event: {e}",
                tenant_id=tenant_id,
                website_id=website_id,
                exc_info=True
            )
            return False

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
        try:
            # Ensure connection (connect() handles connection state internally)
            self.connect()

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

        except Exception as e:
            logger.error(
                f"Failed to publish usage.website.removed event: {e}",
                tenant_id=tenant_id,
                website_id=website_id,
                exc_info=True
            )
            return False


# Global usage event publisher instance
usage_publisher = UsageEventPublisher()
