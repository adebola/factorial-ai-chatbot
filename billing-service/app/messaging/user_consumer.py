"""
RabbitMQ consumer for user creation events from authorization server.

This consumer listens for user creation events and automatically creates
a Basic plan subscription with a 14-day trial starting from the user's
registration date.
"""
import json
import logging
import pika
import os
from datetime import timedelta
from typing import Dict, Any
from dateutil import parser

from ..core.database import get_db
from ..services.subscription_service import SubscriptionService
from ..services.plan_service import PlanService
from ..services.rabbitmq_service import rabbitmq_service
from ..models.subscription import BillingCycle

logger = logging.getLogger(__name__)


class UserEventConsumer:
    """Consumer for user creation events from authorization server"""

    def __init__(self):
        self.rabbitmq_url = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
        self.exchange_name = "billing.events"
        self.queue_name = "billing.user.events"
        self.routing_key = "user.created"

    def connect(self):
        """Establish connection to RabbitMQ"""
        try:
            # Parse connection parameters
            parameters = pika.URLParameters(self.rabbitmq_url)
            parameters.heartbeat = 600
            parameters.blocked_connection_timeout = 300

            # Create connection
            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()

            # Declare exchange (topic exchange for routing)
            channel.exchange_declare(
                exchange=self.exchange_name,
                exchange_type='topic',
                durable=True
            )

            # Declare queue
            channel.queue_declare(queue=self.queue_name, durable=True)

            # Bind queue to exchange with routing key
            channel.queue_bind(
                exchange=self.exchange_name,
                queue=self.queue_name,
                routing_key=self.routing_key
            )

            logger.info(f"Connected to RabbitMQ: {self.queue_name} bound to {self.exchange_name} with key {self.routing_key}")

            return connection, channel

        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            raise

    def handle_user_created(self, message: Dict[str, Any]) -> bool:
        """
        Handle user creation event by creating a Basic plan subscription.

        Args:
            message: User creation event with tenant_id and created_at

        Returns:
            bool: True if successfully processed, False otherwise
        """
        tenant_id = message.get("tenant_id")
        created_at_str = message.get("created_at")

        if not tenant_id or not created_at_str:
            logger.error(f"Invalid message: missing tenant_id or created_at - {message}")
            return False

        # Get database session
        db = next(get_db())

        try:
            subscription_service = SubscriptionService(db)
            plan_service = PlanService(db)

            # IDEMPOTENCY CHECK: Check if subscription already exists
            existing = subscription_service.get_subscription_by_tenant(tenant_id)
            if existing:
                logger.info(f"Subscription already exists for tenant {tenant_id} - skipping creation (idempotency)")
                return True

            # Parse registration date
            try:
                registration_date = parser.isoparse(created_at_str)
            except Exception as e:
                logger.error(f"Failed to parse created_at date '{created_at_str}': {e}")
                return False

            # Get Basic plan (free-tier plan)
            basic_plan = plan_service.get_plan_by_name("Basic")
            if not basic_plan or not basic_plan.is_active:
                logger.error("Basic plan not found or inactive - cannot create subscription")
                return False

            # Calculate 14-day trial end date from registration
            trial_end = registration_date + timedelta(days=14)

            logger.info(
                f"Creating subscription for tenant {tenant_id}: "
                f"Plan={basic_plan.name}, Trial ends={trial_end.isoformat()}"
            )

            # Create subscription with custom trial end
            subscription = subscription_service.create_subscription(
                tenant_id=tenant_id,
                plan_id=basic_plan.id,
                billing_cycle=BillingCycle.MONTHLY,
                start_trial=False,  # Use custom_trial_end instead
                custom_trial_end=trial_end,
                metadata={
                    "created_via": "user_event_consumer",
                    "registration_date": registration_date.isoformat(),
                    "initial_subscription": True
                }
            )

            logger.info(
                f"✅ Successfully created subscription {subscription.id} for tenant {tenant_id}. "
                f"Status: {subscription.status.value}, Trial ends: {trial_end.date()}"
            )

            # Publish subscription_created event to authorization server
            try:
                rabbitmq_published = rabbitmq_service.publish_plan_update(
                    tenant_id=tenant_id,
                    subscription_id=subscription.id,
                    plan_id=basic_plan.id,
                    action="subscription_created"
                )

                if rabbitmq_published:
                    logger.info(
                        f"✅ Published subscription_created event to authorization server: "
                        f"tenant={tenant_id}, subscription={subscription.id}, plan={basic_plan.id}"
                    )
                else:
                    logger.warning(
                        f"⚠️ Failed to publish subscription_created event to authorization server "
                        f"(subscription was created but tenant may not be updated with subscription_id)"
                    )

            except Exception as e:
                logger.error(
                    f"❌ Error publishing subscription_created event to authorization server: {e}",
                    exc_info=True
                )
                # Don't fail the entire operation if RabbitMQ publish fails
                # The subscription was created successfully

            return True

        except Exception as e:
            logger.error(f"❌ Failed to create subscription for tenant {tenant_id}: {e}", exc_info=True)
            db.rollback()
            return False

        finally:
            db.close()

    def callback(self, ch, method, properties, body):
        """
        Callback function for processing messages from queue.

        Args:
            ch: Channel
            method: Delivery method
            properties: Message properties
            body: Message body (JSON)
        """
        try:
            # Parse message
            message = json.loads(body)
            logger.info(f"Received user.created event: {message}")

            # Process message
            success = self.handle_user_created(message)

            # Acknowledge message
            if success:
                ch.basic_ack(delivery_tag=method.delivery_tag)
                logger.info(f"✅ Message acknowledged: {method.delivery_tag}")
            else:
                # Reject and don't requeue (send to dead letter queue if configured)
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                logger.warning(f"⚠️ Message rejected (not requeued): {method.delivery_tag}")

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse message body: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            # Reject and don't requeue to avoid infinite loops
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def start_consuming(self):
        """Start consuming messages from queue"""
        connection, channel = self.connect()

        try:
            # Set QoS - process one message at a time
            channel.basic_qos(prefetch_count=1)

            # Start consuming
            channel.basic_consume(
                queue=self.queue_name,
                on_message_callback=self.callback,
                auto_ack=False  # Manual acknowledgment
            )

            logger.info(f"🚀 Started consuming from queue: {self.queue_name}")
            logger.info("Waiting for user creation events. Press CTRL+C to exit.")

            channel.start_consuming()

        except KeyboardInterrupt:
            logger.info("Stopping consumer...")
            channel.stop_consuming()

        except Exception as e:
            logger.error(f"Error in consumer: {e}", exc_info=True)

        finally:
            connection.close()
            logger.info("Connection closed")


def main():
    """Main entry point for running consumer"""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create and start consumer
    consumer = UserEventConsumer()
    consumer.start_consuming()


if __name__ == "__main__":
    main()
