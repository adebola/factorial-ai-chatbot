"""
RabbitMQ Consumer for Usage Events

MIGRATED TO AIO-PIKA: Now uses async-native RabbitMQ operations with automatic reconnection.
Eliminated manual connection management, threading, and retry logic (494→380 lines).

Consumes usage events from other services and updates the UsageTracking table.
Handles: documents, websites, and chat usage tracking.
"""

import json
import logging
import os
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Set

from aio_pika import connect_robust, ExchangeType, Message, DeliveryMode
from aio_pika.abc import AbstractRobustConnection, AbstractIncomingMessage
from aio_pika.exceptions import AMQPException
from sqlalchemy.orm import Session

from ..core.database import SessionLocal
from ..models.subscription import UsageTracking
from ..services.subscription_service import SubscriptionService

logger = logging.getLogger(__name__)


class UsageEventConsumer:
    """
    Async-native consumer for usage events from RabbitMQ using aio-pika.

    Listens to usage.* events and updates the UsageTracking table.
    Features automatic reconnection and robust error handling.
    """

    def __init__(self):
        self.host = os.environ.get("RABBITMQ_HOST", "localhost")
        self.port = int(os.environ.get("RABBITMQ_PORT", "5672"))
        self.username = os.environ.get("RABBITMQ_USER", "guest")
        self.password = os.environ.get("RABBITMQ_PASSWORD", "guest")
        self.vhost = os.environ.get("RABBITMQ_VHOST", "/")

        self.exchange = os.environ.get("RABBITMQ_USAGE_EXCHANGE", "usage.events")
        self.queue = os.environ.get("RABBITMQ_USAGE_QUEUE", "billing.usage.tracking")
        self.routing_key_pattern = "usage.#"  # Match all usage.* routing keys

        self.connection: Optional[AbstractRobustConnection] = None
        self.consume_task: Optional[asyncio.Task] = None

        # Idempotency tracking (in-memory, could be moved to Redis for distributed deployment)
        self.processed_event_ids: Set[str] = set()
        self.max_tracked_events = 10000  # Prevent memory bloat

        logger.info("Usage event consumer initialized (aio-pika)")

    async def connect(self):
        """Establish robust connection with automatic reconnection."""
        if self.connection and not self.connection.is_closed:
            return

        self.connection = await connect_robust(
            host=self.host,
            port=self.port,
            login=self.username,
            password=self.password,
            virtualhost=self.vhost,
            reconnect_interval=1.0
        )

        logger.info(
            f"✓ Connected to RabbitMQ usage consumer",
            extra={
                "host": self.host,
                "exchange": self.exchange,
                "queue": self.queue,
                "routing_key": self.routing_key_pattern
            }
        )

    async def start_consuming(self):
        """Start consuming messages"""
        await self.connect()

        # Create channel with QoS
        channel = await self.connection.channel()
        await channel.set_qos(prefetch_count=1)

        # Declare exchange
        exchange = await channel.declare_exchange(
            self.exchange,
            ExchangeType.TOPIC,
            durable=True
        )

        # Declare queue
        queue = await channel.declare_queue(
            self.queue,
            durable=True
        )

        # Bind queue to exchange
        await queue.bind(exchange, routing_key=self.routing_key_pattern)

        logger.info(
            f"Usage event consumer started, listening to queue: {self.queue}",
            extra={
                "exchange": self.exchange,
                "routing_key": self.routing_key_pattern
            }
        )

        # Start consuming
        self.consume_task = asyncio.create_task(queue.consume(self._on_message))

    async def stop_consuming(self):
        """Stop consuming messages"""
        if self.consume_task:
            self.consume_task.cancel()
            try:
                await self.consume_task
            except asyncio.CancelledError:
                pass

        if self.connection and not self.connection.is_closed:
            await self.connection.close()

        logger.info("Stopped usage event consumer")

    async def _on_message(self, message: AbstractIncomingMessage):
        """
        Handle incoming usage event message

        Args:
            message: Incoming message from RabbitMQ
        """
        async with message.process():
            try:
                # Parse message
                event = json.loads(message.body.decode())
                event_type = message.routing_key

                logger.info(
                    f"✅ Received usage event",
                    extra={
                        "event_type": event_type,
                        "tenant_id": event.get("tenant_id"),
                        "event_id": event.get("event_id")
                    }
                )

                # Check idempotency
                event_id = event.get("event_id")
                if event_id and event_id in self.processed_event_ids:
                    logger.debug(f"Skipping duplicate event: {event_id}")
                    return  # Auto-ack via context manager

                # Process event
                success = await self._process_event(event_type, event)

                if success:
                    # Track processed event
                    if event_id:
                        self.processed_event_ids.add(event_id)
                        # Prevent memory bloat
                        if len(self.processed_event_ids) > self.max_tracked_events:
                            # Remove oldest half
                            self.processed_event_ids = set(
                                list(self.processed_event_ids)[self.max_tracked_events // 2:]
                            )

                    logger.debug(f"Successfully processed event: {event_type}")
                    # Auto-ack via context manager
                else:
                    # Reject and requeue
                    raise Exception(f"Failed to process event: {event_type}")

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse event JSON: {e}", exc_info=True)
                # Reject without requeue (malformed message) - auto-handled by context manager
            except Exception as e:
                logger.error(f"Error processing event: {e}", exc_info=True)
                # Re-raise to trigger nack+requeue via context manager
                raise

    async def _process_event(self, event_type: str, event: Dict[str, Any]) -> bool:
        """
        Process a usage event and update the database

        Args:
            event_type: Type of event (routing key)
            event: Event payload

        Returns:
            True if processed successfully, False otherwise
        """
        tenant_id = event.get("tenant_id")
        if not tenant_id:
            logger.error("Event missing tenant_id", extra={"event": event})
            return False

        db: Session = SessionLocal()
        try:
            subscription_service = SubscriptionService(db)

            # Get or create usage tracking record
            subscription = subscription_service.get_subscription_by_tenant(tenant_id)
            if not subscription:
                logger.warning(f"No subscription found for tenant: {tenant_id}")
                return True  # Acknowledge anyway (tenant might not have subscription yet)

            usage = db.query(UsageTracking).filter(
                UsageTracking.subscription_id == subscription.id
            ).first()

            if not usage:
                # Initialize usage tracking
                subscription_service._initialize_usage_tracking(subscription)
                usage = db.query(UsageTracking).filter(
                    UsageTracking.subscription_id == subscription.id
                ).first()

            # Update usage based on event type
            if event_type in ["usage.document.created", "usage.document.added"]:
                usage.documents_used += 1
                logger.info(f"Incremented documents for tenant {tenant_id}: {usage.documents_used}")

            elif event_type in ["usage.document.deleted", "usage.document.removed"]:
                previous_count = usage.documents_used
                usage.documents_used = max(0, usage.documents_used - 1)

                if previous_count == 0:
                    logger.warning(
                        f"Attempted to decrement documents when already at 0 for tenant {tenant_id}. "
                        f"This indicates a missed 'added' event or duplicate 'removed' event. "
                        f"Counter protected and remains at 0."
                    )
                else:
                    logger.info(f"Decremented documents for tenant {tenant_id}: {usage.documents_used}")

            elif event_type in ["usage.website.created", "usage.website.added"]:
                usage.websites_used += 1
                logger.info(f"Incremented websites for tenant {tenant_id}: {usage.websites_used}")

            elif event_type in ["usage.website.deleted", "usage.website.removed"]:
                previous_count = usage.websites_used
                usage.websites_used = max(0, usage.websites_used - 1)

                if previous_count == 0:
                    logger.warning(
                        f"Attempted to decrement websites when already at 0 for tenant {tenant_id}. "
                        f"This indicates a missed 'added' event or duplicate 'removed' event. "
                        f"Counter protected and remains at 0."
                    )
                else:
                    logger.info(f"Decremented websites for tenant {tenant_id}: {usage.websites_used}")

            elif event_type == "usage.chat.message":
                # Chat messages increment both daily and monthly
                message_count = event.get("message_count", 1)
                usage.daily_chats_used += message_count
                usage.monthly_chats_used += message_count

                # Check if daily reset is needed
                now = datetime.now(timezone.utc)
                if usage.daily_reset_at and now >= usage.daily_reset_at:
                    usage.daily_chats_used = message_count
                    usage.daily_reset_at = now + timedelta(days=1)
                    logger.info(f"Reset daily chats for tenant {tenant_id}")
                elif not usage.daily_reset_at:
                    usage.daily_reset_at = now + timedelta(days=1)

                # Check if monthly reset is needed
                if usage.monthly_reset_at and now >= usage.monthly_reset_at:
                    usage.monthly_chats_used = message_count
                    usage.monthly_reset_at = now + timedelta(days=30)
                    logger.info(f"Reset monthly chats for tenant {tenant_id}")
                elif not usage.monthly_reset_at:
                    usage.monthly_reset_at = now + timedelta(days=30)

                logger.info(
                    f"Incremented chats for tenant {tenant_id}: "
                    f"daily={usage.daily_chats_used}, monthly={usage.monthly_chats_used}"
                )
            else:
                logger.warning(f"Unknown event type: {event_type}")
                return True  # Acknowledge unknown events

            usage.updated_at = datetime.now(timezone.utc)
            db.commit()

            # Check limits and publish warning if exceeded
            await self._check_and_publish_limit_warning(db, tenant_id, usage, subscription, event_type)

            return True

        except Exception as e:
            db.rollback()
            logger.error(f"Failed to process usage event: {e}", exc_info=True)
            return False
        finally:
            db.close()

    async def _check_and_publish_limit_warning(
        self,
        db: Session,
        tenant_id: str,
        usage: UsageTracking,
        subscription: Any,
        event_type: str
    ):
        """
        Check if usage limits are exceeded and publish warning events.

        Args:
            db: Database session
            tenant_id: Tenant ID
            usage: UsageTracking record
            subscription: Subscription record
            event_type: Type of usage event that triggered this check
        """
        try:
            # Get plan limits
            from ..models.plan import Plan
            plan = None
            if subscription and subscription.plan_id:
                plan = db.query(Plan).filter(Plan.id == subscription.plan_id).first()

            if not plan:
                return

            # Check chat limits (daily and monthly)
            if event_type == "usage.chat.message":
                # Check daily limit
                if plan.daily_chat_limit > 0:
                    if usage.daily_chats_used >= plan.daily_chat_limit:
                        await self._publish_limit_warning(
                            tenant_id=tenant_id,
                            usage_type="daily_chats",
                            current_usage=usage.daily_chats_used,
                            limit=plan.daily_chat_limit,
                            warning_type="exceeded"
                        )
                    elif usage.daily_chats_used >= plan.daily_chat_limit * 0.9:
                        await self._publish_limit_warning(
                            tenant_id=tenant_id,
                            usage_type="daily_chats",
                            current_usage=usage.daily_chats_used,
                            limit=plan.daily_chat_limit,
                            warning_type="approaching"
                        )

                # Check monthly limit
                if plan.monthly_chat_limit > 0:
                    if usage.monthly_chats_used >= plan.monthly_chat_limit:
                        await self._publish_limit_warning(
                            tenant_id=tenant_id,
                            usage_type="monthly_chats",
                            current_usage=usage.monthly_chats_used,
                            limit=plan.monthly_chat_limit,
                            warning_type="exceeded"
                        )
                    elif usage.monthly_chats_used >= plan.monthly_chat_limit * 0.9:
                        await self._publish_limit_warning(
                            tenant_id=tenant_id,
                            usage_type="monthly_chats",
                            current_usage=usage.monthly_chats_used,
                            limit=plan.monthly_chat_limit,
                            warning_type="approaching"
                        )

        except Exception as e:
            logger.error(f"Failed to check/publish limit warning: {e}", exc_info=True)

    async def _publish_limit_warning(
        self,
        tenant_id: str,
        usage_type: str,
        current_usage: int,
        limit: int,
        warning_type: str
    ):
        """
        Publish a limit warning event.

        Args:
            tenant_id: Tenant ID
            usage_type: Type of usage (daily_chats, monthly_chats, etc.)
            current_usage: Current usage count
            limit: Usage limit
            warning_type: "exceeded" or "approaching"
        """
        try:
            # Determine routing key
            if warning_type == "exceeded":
                routing_key = "usage.limit.exceeded"
            else:
                routing_key = "usage.limit.warning"

            # Build event payload
            event = {
                "event_id": str(uuid.uuid4()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "tenant_id": tenant_id,
                "usage_type": usage_type,
                "current_usage": current_usage,
                "limit": limit,
                "percentage": int((current_usage / limit) * 100) if limit > 0 else 0,
                "warning_type": warning_type
            }

            # Publish using the existing connection
            async with self.connection.channel() as channel:
                exchange = await channel.declare_exchange(
                    self.exchange,
                    ExchangeType.TOPIC,
                    durable=True
                )

                message = Message(
                    body=json.dumps(event).encode(),
                    delivery_mode=DeliveryMode.PERSISTENT,
                    content_type="application/json",
                    timestamp=datetime.now(timezone.utc)
                )

                await exchange.publish(message, routing_key=routing_key)

            logger.info(
                f"Published {warning_type} limit warning",
                extra={
                    "tenant_id": tenant_id,
                    "usage_type": usage_type,
                    "current_usage": current_usage,
                    "limit": limit,
                    "routing_key": routing_key
                }
            )

        except Exception as e:
            logger.error(f"Failed to publish limit warning: {e}", exc_info=True)


# Global consumer instance
usage_consumer = UsageEventConsumer()
