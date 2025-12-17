"""
RabbitMQ Consumer for Usage Events

Consumes usage events from other services and updates the UsageTracking table.
Handles: documents, websites, and chat usage tracking.
"""

import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
import pika
from pika.exceptions import AMQPConnectionError, AMQPChannelError
from sqlalchemy.orm import Session

from ..core.database import SessionLocal
from ..models.subscription import UsageTracking
from ..services.subscription_service import SubscriptionService

logger = logging.getLogger(__name__)


class UsageEventConsumer:
    """
    Consumer for usage events from RabbitMQ.

    Listens to usage.* events and updates the UsageTracking table.
    """

    def __init__(self):
        self.host = os.environ.get("RABBITMQ_HOST", "localhost")
        self.port = int(os.environ.get("RABBITMQ_PORT", "5672"))
        self.username = os.environ.get("RABBITMQ_USER", "guest")  # Match chat-service
        self.password = os.environ.get("RABBITMQ_PASSWORD", "guest")
        self.vhost = os.environ.get("RABBITMQ_VHOST", "/")

        self.exchange = os.environ.get("RABBITMQ_USAGE_EXCHANGE", "usage.events")
        self.queue = os.environ.get("RABBITMQ_USAGE_QUEUE", "billing.usage.tracking")
        self.routing_key_pattern = "usage.*"

        self.connection = None
        self.channel = None
        self.consumer_thread = None
        self.is_running = False

        # Idempotency tracking (in-memory, could be moved to Redis for distributed deployment)
        self.processed_event_ids = set()
        self.max_tracked_events = 10000  # Prevent memory bloat

    def connect(self, max_retries: int = 5, initial_delay: float = 1.0):
        """
        Establish connection to RabbitMQ with exponential backoff retry logic.

        Args:
            max_retries: Maximum number of connection attempts
            initial_delay: Initial delay in seconds before first retry
        """
        retry_count = 0
        delay = initial_delay

        while retry_count < max_retries:
            try:
                credentials = pika.PlainCredentials(self.username, self.password)
                parameters = pika.ConnectionParameters(
                    host=self.host,
                    port=self.port,
                    virtual_host=self.vhost,
                    credentials=credentials,
                    heartbeat=600,
                    blocked_connection_timeout=300,
                    connection_attempts=3,
                    retry_delay=2
                )

                self.connection = pika.BlockingConnection(parameters)
                self.channel = self.connection.channel()

                # Declare exchange (idempotent)
                self.channel.exchange_declare(
                    exchange=self.exchange,
                    exchange_type='topic',
                    durable=True
                )

                # Declare queue (idempotent)
                self.channel.queue_declare(
                    queue=self.queue,
                    durable=True
                )

                # Bind queue to exchange
                self.channel.queue_bind(
                    exchange=self.exchange,
                    queue=self.queue,
                    routing_key=self.routing_key_pattern
                )

                # Set QoS - process one message at a time
                self.channel.basic_qos(prefetch_count=1)

                logger.info(
                    f"Connected to RabbitMQ and bound queue",
                    extra={
                        "host": self.host,
                        "exchange": self.exchange,
                        "queue": self.queue,
                        "routing_key": self.routing_key_pattern,
                        "retry_count": retry_count
                    }
                )
                return  # Success - exit the retry loop

            except (AMQPConnectionError, ConnectionRefusedError) as e:
                retry_count += 1
                if retry_count >= max_retries:
                    logger.error(
                        f"Failed to connect to RabbitMQ after {max_retries} attempts: {e}",
                        exc_info=True
                    )
                    raise

                logger.warning(
                    f"Failed to connect to RabbitMQ (attempt {retry_count}/{max_retries}): {e}. "
                    f"Retrying in {delay:.1f} seconds..."
                )
                time.sleep(delay)
                delay *= 2  # Exponential backoff

            except Exception as e:
                logger.error(f"Unexpected error connecting to RabbitMQ: {e}", exc_info=True)
                raise

    def start_consuming(self):
        """Start consuming messages in a background thread"""
        if self.is_running:
            logger.warning("Consumer is already running")
            return

        self.is_running = True
        self.consumer_thread = threading.Thread(target=self._consume_loop, daemon=True)
        self.consumer_thread.start()
        logger.info("Started usage event consumer thread")

    def stop_consuming(self):
        """Stop consuming messages"""
        self.is_running = False
        if self.channel and self.channel.is_open:
            self.channel.stop_consuming()
        if self.connection and self.connection.is_open:
            self.connection.close()
        logger.info("Stopped usage event consumer")

    def _consume_loop(self):
        """Main consumption loop (runs in background thread)"""
        try:
            logger.info(f"Usage event consumer started, listening to queue: {self.queue}")
            self.channel.basic_consume(
                queue=self.queue,
                on_message_callback=self._on_message,
                auto_ack=False  # Manual acknowledgment for reliability
            )
            self.channel.start_consuming()
        except Exception as e:
            logger.error(f"Consumer loop error: {e}", exc_info=True)
            self.is_running = False

    def _on_message(self, ch, method, properties, body):
        """
        Handle incoming usage event message

        Args:
            ch: Channel
            method: Delivery method
            properties: Message properties
            body: Message body (JSON)
        """
        try:
            # Parse message
            event = json.loads(body)
            event_type = method.routing_key

            logger.debug(
                f"Received usage event",
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
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            # Process event based on type
            success = self._process_event(event_type, event)

            if success:
                # Track processed event
                if event_id:
                    self.processed_event_ids.add(event_id)
                    # Prevent memory bloat
                    if len(self.processed_event_ids) > self.max_tracked_events:
                        # Remove oldest half
                        self.processed_event_ids = set(list(self.processed_event_ids)[self.max_tracked_events // 2:])

                # Acknowledge message
                ch.basic_ack(delivery_tag=method.delivery_tag)
                logger.debug(f"Successfully processed event: {event_type}")
            else:
                # Reject and requeue (will retry)
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                logger.warning(f"Failed to process event, requeuing: {event_type}")

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse event JSON: {e}", exc_info=True)
            # Reject without requeue (malformed message)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        except Exception as e:
            logger.error(f"Error processing event: {e}", exc_info=True)
            # Reject and requeue
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

    def _process_event(self, event_type: str, event: Dict[str, Any]) -> bool:
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
                usage.documents_used = max(0, usage.documents_used - 1)
                logger.info(f"Decremented documents for tenant {tenant_id}: {usage.documents_used}")

            elif event_type in ["usage.website.created", "usage.website.added"]:
                usage.websites_used += 1
                logger.info(f"Incremented websites for tenant {tenant_id}: {usage.websites_used}")

            elif event_type in ["usage.website.deleted", "usage.website.removed"]:
                usage.websites_used = max(0, usage.websites_used - 1)
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
            self._check_and_publish_limit_warning(tenant_id, usage, subscription, event_type)

            return True

        except Exception as e:
            db.rollback()
            logger.error(f"Failed to process usage event: {e}", exc_info=True)
            return False
        finally:
            db.close()

    def _check_and_publish_limit_warning(
        self,
        tenant_id: str,
        usage: UsageTracking,
        subscription: Any,
        event_type: str
    ):
        """
        Check if usage limits are exceeded and publish warning events.

        Args:
            tenant_id: Tenant ID
            usage: UsageTracking record
            subscription: Subscription record
            event_type: Type of usage event that triggered this check
        """
        try:
            # Get plan limits
            plan = subscription.plan if subscription else None
            if not plan:
                return

            # Check chat limits (daily and monthly)
            if event_type == "usage.chat.message":
                # Check daily limit
                if plan.daily_chat_limit > 0:
                    if usage.daily_chats_used >= plan.daily_chat_limit:
                        self._publish_limit_warning(
                            tenant_id=tenant_id,
                            usage_type="daily_chats",
                            current_usage=usage.daily_chats_used,
                            limit=plan.daily_chat_limit,
                            warning_type="exceeded"
                        )
                    elif usage.daily_chats_used >= plan.daily_chat_limit * 0.9:
                        # Warning at 90% threshold
                        self._publish_limit_warning(
                            tenant_id=tenant_id,
                            usage_type="daily_chats",
                            current_usage=usage.daily_chats_used,
                            limit=plan.daily_chat_limit,
                            warning_type="approaching"
                        )

                # Check monthly limit
                if plan.monthly_chat_limit > 0:
                    if usage.monthly_chats_used >= plan.monthly_chat_limit:
                        self._publish_limit_warning(
                            tenant_id=tenant_id,
                            usage_type="monthly_chats",
                            current_usage=usage.monthly_chats_used,
                            limit=plan.monthly_chat_limit,
                            warning_type="exceeded"
                        )
                    elif usage.monthly_chats_used >= plan.monthly_chat_limit * 0.9:
                        self._publish_limit_warning(
                            tenant_id=tenant_id,
                            usage_type="monthly_chats",
                            current_usage=usage.monthly_chats_used,
                            limit=plan.monthly_chat_limit,
                            warning_type="approaching"
                        )

        except Exception as e:
            logger.error(f"Failed to check/publish limit warning: {e}", exc_info=True)

    def _publish_limit_warning(
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

            # Publish to exchange
            self.channel.basic_publish(
                exchange=self.exchange,
                routing_key=routing_key,
                body=json.dumps(event),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Persistent message
                    content_type='application/json',
                    timestamp=int(datetime.now(timezone.utc).timestamp())
                )
            )

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
