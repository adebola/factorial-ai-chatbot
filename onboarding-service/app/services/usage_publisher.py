"""
RabbitMQ Publisher for Usage Events

MIGRATED TO AIO-PIKA: Now uses async-native RabbitMQ operations with automatic reconnection.
Eliminated 400+ lines of manual connection management, threading locks, and retry logic.

Publishes usage events to the billing service when documents/websites are added or removed.
"""

import json
import os
from datetime import datetime
from typing import Optional

from aio_pika import connect_robust, Message, ExchangeType, DeliveryMode
from aio_pika.abc import AbstractRobustConnection
from aio_pika.exceptions import AMQPException

from ..core.logging_config import get_logger

logger = get_logger(__name__)


class UsageEventPublisher:
    """
    Async-native usage event publisher using aio-pika with automatic reconnection.

    Publishes events when resources are added or removed:
    - usage.document.added
    - usage.document.removed
    - usage.website.added
    - usage.website.removed
    """

    def __init__(self):
        self.connection: Optional[AbstractRobustConnection] = None

        # Get RabbitMQ config from environment
        self.rabbitmq_host = os.environ.get("RABBITMQ_HOST", "localhost")
        self.rabbitmq_port = int(os.environ.get("RABBITMQ_PORT", "5672"))
        self.rabbitmq_user = os.environ.get("RABBITMQ_USER", "guest")
        self.rabbitmq_password = os.environ.get("RABBITMQ_PASSWORD", "guest")
        self.rabbitmq_vhost = os.environ.get("RABBITMQ_VHOST", "/")

        # Usage exchange for billing service
        self.usage_exchange = os.environ.get("RABBITMQ_USAGE_EXCHANGE", "usage.events")

        logger.info("Usage event publisher initialized (aio-pika)")

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
            reconnect_interval=1.0,
            fail_fast=False
        )

        logger.info(
            "✓ Successfully connected to RabbitMQ usage event publisher",
            host=self.rabbitmq_host,
            port=self.rabbitmq_port,
            exchange=self.usage_exchange
        )

    async def close(self):
        """Close RabbitMQ connection gracefully."""
        if self.connection and not self.connection.is_closed:
            await self.connection.close()
            logger.info("Closed RabbitMQ usage publisher connection")

    async def publish_document_added(
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
            await self.connect()

            event = {
                "event_type": "usage.document.added",
                "tenant_id": tenant_id,
                "document_id": document_id,
                "filename": filename,
                "file_size": file_size,
                "count": 1,  # Incrementing by 1
                "timestamp": datetime.utcnow().isoformat()
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

                await exchange.publish(message, routing_key="usage.document.added")

            logger.debug(
                "Published usage.document.added event",
                tenant_id=tenant_id,
                document_id=document_id,
                filename=filename
            )

            return True

        except Exception as e:
            logger.error(
                f"Failed to publish document_added event: {e}",
                tenant_id=tenant_id,
                document_id=document_id,
                exc_info=True
            )
            return False

    async def publish_document_removed(
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
            await self.connect()

            event = {
                "event_type": "usage.document.removed",
                "tenant_id": tenant_id,
                "document_id": document_id,
                "filename": filename,
                "count": -1,  # Decrementing by 1
                "timestamp": datetime.utcnow().isoformat()
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

                await exchange.publish(message, routing_key="usage.document.removed")

            logger.debug(
                "Published usage.document.removed event",
                tenant_id=tenant_id,
                document_id=document_id,
                filename=filename
            )

            return True

        except Exception as e:
            logger.error(
                f"Failed to publish document_removed event: {e}",
                tenant_id=tenant_id,
                document_id=document_id,
                exc_info=True
            )
            return False

    async def publish_website_added(
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
            await self.connect()

            event = {
                "event_type": "usage.website.added",
                "tenant_id": tenant_id,
                "website_id": website_id,
                "url": url,
                "pages_scraped": pages_scraped,
                "count": 1,  # Incrementing by 1
                "timestamp": datetime.utcnow().isoformat()
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

                await exchange.publish(message, routing_key="usage.website.added")

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
                f"Failed to publish website_added event: {e}",
                tenant_id=tenant_id,
                website_id=website_id,
                exc_info=True
            )
            return False

    async def publish_website_removed(
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
            await self.connect()

            event = {
                "event_type": "usage.website.removed",
                "tenant_id": tenant_id,
                "website_id": website_id,
                "url": url,
                "count": -1,  # Decrementing by 1
                "timestamp": datetime.utcnow().isoformat()
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

                await exchange.publish(message, routing_key="usage.website.removed")

            logger.debug(
                "Published usage.website.removed event",
                tenant_id=tenant_id,
                website_id=website_id,
                url=url
            )

            return True

        except Exception as e:
            logger.error(
                f"Failed to publish website_removed event: {e}",
                tenant_id=tenant_id,
                website_id=website_id,
                exc_info=True
            )
            return False


# Global usage event publisher instance
usage_publisher = UsageEventPublisher()