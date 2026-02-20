"""
RabbitMQ Workflow Event Consumer

Listens for workflow lifecycle events (created/deleted/activated/deactivated)
from the workflow service and invalidates the Redis has_workflows cache
so the chat service picks up changes immediately.
"""

import json
import os
import asyncio
from typing import Optional

from aio_pika import connect_robust, ExchangeType
from aio_pika.abc import AbstractRobustConnection, AbstractIncomingMessage

import redis.asyncio as aioredis

from ..core.logging_config import get_logger

logger = get_logger(__name__)


class WorkflowEventConsumer:
    """
    Async-native consumer for workflow lifecycle events.

    Listens for:
    - workflow.changed — When a workflow is created, deleted, activated, or deactivated

    Actions:
    - Sets Redis key workflow:has_workflows:{tenant_id} to "1"
      (a change means workflows exist or were modified — the actual
      check_triggers call will determine if they match)
    """

    def __init__(self):
        self.rabbitmq_host = os.environ.get("RABBITMQ_HOST", "localhost")
        self.rabbitmq_port = int(os.environ.get("RABBITMQ_PORT", "5672"))
        self.rabbitmq_user = os.environ.get("RABBITMQ_USER", "guest")
        self.rabbitmq_password = os.environ.get("RABBITMQ_PASSWORD", "guest")
        self.rabbitmq_vhost = os.environ.get("RABBITMQ_VHOST", "/")

        self.exchange_name = "workflow.events"
        self.queue_name = "chat-service.workflow-events"

        self.connection: Optional[AbstractRobustConnection] = None
        self.consume_task: Optional[asyncio.Task] = None
        self._redis: Optional[aioredis.Redis] = None

        logger.info("Workflow event consumer initialized (aio-pika)")

    async def _get_redis(self) -> aioredis.Redis:
        """Get or create async Redis client."""
        if self._redis is None:
            redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
            self._redis = aioredis.from_url(redis_url, decode_responses=True)
        return self._redis

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
            "Connected to RabbitMQ for workflow event consumption",
            extra={
                "host": self.rabbitmq_host,
                "port": self.rabbitmq_port,
                "exchange": self.exchange_name,
                "queue": self.queue_name
            }
        )

    async def start(self):
        """Start consuming workflow events."""
        await self.connect()

        channel = await self.connection.channel()
        await channel.set_qos(prefetch_count=10)

        exchange = await channel.declare_exchange(
            self.exchange_name,
            ExchangeType.TOPIC,
            durable=True
        )

        queue = await channel.declare_queue(
            self.queue_name,
            durable=True
        )

        await queue.bind(exchange, routing_key="workflow.changed")

        logger.info(
            "Workflow event consumer started - listening for events",
            extra={
                "exchange": self.exchange_name,
                "queue": self.queue_name,
                "routing_keys": ["workflow.changed"]
            }
        )

        self.consume_task = asyncio.create_task(queue.consume(self._on_message))

    async def stop(self):
        """Stop consuming workflow events."""
        if self.consume_task:
            self.consume_task.cancel()
            try:
                await self.consume_task
            except asyncio.CancelledError:
                pass

        if self.connection and not self.connection.is_closed:
            await self.connection.close()

        if self._redis:
            await self._redis.close()
            self._redis = None

        logger.info("Workflow event consumer stopped")

    async def _on_message(self, message: AbstractIncomingMessage):
        """Handle incoming workflow lifecycle event."""
        async with message.process():
            try:
                event = json.loads(message.body.decode())

                tenant_id = event.get("tenant_id")
                action = event.get("action")
                workflow_id = event.get("workflow_id")

                logger.info(
                    f"Received workflow event: {action}",
                    extra={
                        "tenant_id": tenant_id,
                        "action": action,
                        "workflow_id": workflow_id
                    }
                )

                if tenant_id:
                    cache_key = f"workflow:has_workflows:{tenant_id}"
                    try:
                        r = await self._get_redis()
                        # Set to "1" — a change means workflows exist or were modified.
                        # For "deleted"/"deactivated", we still set "1" and let the
                        # TTL-based refresh or next cache miss do the accurate check.
                        # This is safe because setting "1" only means "check workflows",
                        # not "definitely has workflows".
                        await r.setex(cache_key, 300, "1")
                        logger.info(
                            f"Workflow cache updated for tenant {tenant_id} due to {action}"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to update workflow cache: {e}")

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse workflow event message: {e}")

            except Exception as e:
                logger.exception(f"Error handling workflow event: {e}")


# Global consumer instance
workflow_event_consumer = WorkflowEventConsumer()
