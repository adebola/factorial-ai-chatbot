"""
RabbitMQ service for publishing messages to the authorization server.

MIGRATED TO AIO-PIKA: Now uses async-native RabbitMQ operations with automatic reconnection.
"""
import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from aio_pika import connect_robust, Message, ExchangeType, DeliveryMode
from aio_pika.abc import AbstractRobustConnection
from aio_pika.exceptions import AMQPException

logger = logging.getLogger(__name__)


class RabbitMQService:
    """Async-native RabbitMQ service using aio-pika with automatic reconnection."""

    def __init__(self):
        self.host = os.environ.get("RABBITMQ_HOST", "localhost")
        self.port = int(os.environ.get("RABBITMQ_PORT", "5672"))
        self.username = os.environ.get("RABBITMQ_USER", "guest")
        self.password = os.environ.get("RABBITMQ_PASSWORD", "guest")
        self.exchange = os.environ.get("RABBITMQ_EXCHANGE", "topic-exchange")
        self.plan_update_routing_key = os.environ.get("RABBITMQ_PLAN_UPDATE_ROUTING_KEY", "plan.update")
        self.logo_update_routing_key = os.environ.get("RABBITMQ_LOGO_UPDATE_ROUTING_KEY", "logo.update")

        self.connection: Optional[AbstractRobustConnection] = None

        logger.info("RabbitMQ service initialized (aio-pika)")

    async def connect(self):
        """Establish robust connection with automatic reconnection."""
        if self.connection and not self.connection.is_closed:
            return

        self.connection = await connect_robust(
            host=self.host,
            port=self.port,
            login=self.username,
            password=self.password,
            reconnect_interval=1.0)

        logger.info(f"Connected to RabbitMQ at {self.host}:{self.port}")

    async def publish_plan_update(
        self,
        tenant_id: str,
        subscription_id: str,
        plan_id: str,
        action: str = "subscription_created"
    ) -> bool:
        """
        Publish a plan update message to RabbitMQ

        Args:
            tenant_id: The tenant UUID
            subscription_id: The subscription UUID
            plan_id: The plan UUID
            action: The action type (subscription_created, plan_switched, etc.)

        Returns:
            True if message was published successfully, False otherwise
        """
        try:
            await self.connect()

            # Create message payload
            message_data = {
                "tenant_id": tenant_id,
                "subscription_id": subscription_id,
                "plan_id": plan_id,
                "action": action,
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
            }

            async with self.connection.channel() as channel:
                exchange = await channel.declare_exchange(
                    self.exchange,
                    ExchangeType.TOPIC,
                    durable=True
                )

                message = Message(
                    body=json.dumps(message_data).encode(),
                    delivery_mode=DeliveryMode.PERSISTENT,
                    content_type="application/json"
                )

                await exchange.publish(message, routing_key=self.plan_update_routing_key)

            logger.info(
                f"Published plan update message for tenant {tenant_id} "
                f"with subscription {subscription_id} and plan {plan_id} (action: {action})"
            )
            return True

        except Exception as e:
            logger.exception(f"Failed to publish plan update message: {e}")
            return False

    async def publish_plan_switch(
        self,
        tenant_id: str,
        subscription_id: str,
        old_plan_id: str,
        new_plan_id: str
    ) -> bool:
        """
        Publish a plan switch message to RabbitMQ

        Args:
            tenant_id: The tenant UUID
            subscription_id: The subscription UUID
            old_plan_id: The previous plan UUID
            new_plan_id: The new plan UUID

        Returns:
            True if message was published successfully, False otherwise
        """
        try:
            await self.connect()

            # Create message payload with both old and new plan
            message_data = {
                "tenant_id": tenant_id,
                "subscription_id": subscription_id,
                "plan_id": new_plan_id,  # The new plan becomes the current plan
                "old_plan_id": old_plan_id,
                "action": "plan_switched",
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
            }

            async with self.connection.channel() as channel:
                exchange = await channel.declare_exchange(
                    self.exchange,
                    ExchangeType.TOPIC,
                    durable=True
                )

                message = Message(
                    body=json.dumps(message_data).encode(),
                    delivery_mode=DeliveryMode.PERSISTENT,
                    content_type="application/json"
                )

                await exchange.publish(message, routing_key=self.plan_update_routing_key)

            logger.info(
                f"Published plan switch message for tenant {tenant_id} "
                f"with subscription {subscription_id} from plan {old_plan_id} to {new_plan_id}"
            )
            return True

        except Exception as e:
            logger.exception(f"Failed to publish plan switch message: {e}")
            return False

    async def publish_logo_event(
        self,
        tenant_id: str,
        event_type: str,
        logo_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Publish a logo event message to RabbitMQ

        Args:
            tenant_id: The tenant UUID
            event_type: The event type (logo_uploaded, logo_deleted, logo_updated)
            logo_data: Optional dictionary with logo information

        Returns:
            True if message was published successfully, False otherwise
        """
        try:
            await self.connect()

            # Create message payload with comprehensive schema
            message_data = {
                "event_type": event_type,
                "tenant_id": tenant_id,
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                "data": logo_data or {}
            }

            async with self.connection.channel() as channel:
                exchange = await channel.declare_exchange(
                    self.exchange,
                    ExchangeType.TOPIC,
                    durable=True
                )

                message = Message(
                    body=json.dumps(message_data).encode(),
                    delivery_mode=DeliveryMode.PERSISTENT,
                    content_type="application/json",
                    headers={
                        "event_type": event_type,
                        "tenant_id": tenant_id
                    }
                )

                await exchange.publish(message, routing_key=self.logo_update_routing_key)

            logger.info(
                f"Published logo event '{event_type}' for tenant {tenant_id}"
            )
            return True

        except Exception as e:
            logger.exception(f"Failed to publish logo event message: {e}")
            return False

    async def publish_logo_uploaded(
        self,
        tenant_id: str,
        logo_url: str
    ) -> bool:
        """Publish logo uploaded event"""
        logo_data = {
            "logo_url": logo_url
        }
        return await self.publish_logo_event(tenant_id, "logo_uploaded", logo_data)

    async def publish_logo_deleted(self, tenant_id: str) -> bool:
        """Publish logo deleted event"""
        return await self.publish_logo_event(tenant_id, "logo_deleted")

    async def publish_logo_updated(
        self,
        tenant_id: str,
        logo_url: str
    ) -> bool:
        """Publish logo updated event (for backwards compatibility)"""
        return await self.publish_logo_uploaded(tenant_id, logo_url)

    async def health_check(self) -> bool:
        """Check if RabbitMQ is accessible"""
        try:
            await self.connect()
            return True
        except Exception:
            return False

    async def close(self):
        """Close connection gracefully."""
        if self.connection and not self.connection.is_closed:
            await self.connection.close()
            logger.info("RabbitMQ service connection closed")


# Create a singleton instance
rabbitmq_service = RabbitMQService()