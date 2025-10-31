"""RabbitMQ service for publishing messages to the authorization server"""
import json
import logging
import os
import time
from datetime import datetime
from typing import Dict, Any, Optional
import pika
from pika.exceptions import AMQPConnectionError, AMQPChannelError

logger = logging.getLogger(__name__)


class RabbitMQService:
    """Service for publishing messages to RabbitMQ"""
    
    def __init__(self):
        self.host = os.environ.get("RABBITMQ_HOST", "localhost")
        self.port = int(os.environ.get("RABBITMQ_PORT", "5672"))
        self.username = os.environ.get("RABBITMQ_USERNAME", "guest")
        self.password = os.environ.get("RABBITMQ_PASSWORD", "guest")
        self.exchange = os.environ.get("RABBITMQ_EXCHANGE", "topic-exchange")
        self.plan_update_routing_key = os.environ.get("RABBITMQ_PLAN_UPDATE_ROUTING_KEY", "plan.update")
        self.logo_update_routing_key = os.environ.get("RABBITMQ_LOGO_UPDATE_ROUTING_KEY", "logo.update")
        
        self.connection = None
        self.channel = None
        
    def _connect(self, max_retries: int = 3, initial_delay: float = 0.5) -> bool:
        """
        Establish connection to RabbitMQ with retry logic.

        Args:
            max_retries: Maximum number of connection attempts
            initial_delay: Initial delay in seconds before first retry

        Returns:
            True if connection successful, False otherwise
        """
        try:
            if self.connection and not self.connection.is_closed:
                return True

            retry_count = 0
            delay = initial_delay

            while retry_count < max_retries:
                try:
                    credentials = pika.PlainCredentials(self.username, self.password)
                    parameters = pika.ConnectionParameters(
                        host=self.host,
                        port=self.port,
                        credentials=credentials,
                        heartbeat=600,
                        blocked_connection_timeout=300,
                        connection_attempts=2,
                        retry_delay=1
                    )

                    self.connection = pika.BlockingConnection(parameters)
                    self.channel = self.connection.channel()

                    # Declare the exchange (should match auth server configuration)
                    self.channel.exchange_declare(
                        exchange=self.exchange,
                        exchange_type='topic',
                        durable=True
                    )

                    logger.info(
                        f"Connected to RabbitMQ at {self.host}:{self.port}",
                        extra={"retry_count": retry_count}
                    )
                    return True

                except (AMQPConnectionError, ConnectionRefusedError) as e:
                    retry_count += 1
                    if retry_count >= max_retries:
                        logger.error(
                            f"Failed to connect to RabbitMQ after {max_retries} attempts: {e}"
                        )
                        return False

                    logger.warning(
                        f"Failed to connect to RabbitMQ (attempt {retry_count}/{max_retries}): {e}. "
                        f"Retrying in {delay:.1f} seconds..."
                    )
                    time.sleep(delay)
                    delay *= 2  # Exponential backoff

            return False

        except Exception as e:
            logger.error(f"Unexpected error connecting to RabbitMQ: {e}")
            return False
    
    def _disconnect(self):
        """Close connection to RabbitMQ"""
        try:
            if self.channel and not self.channel.is_closed:
                self.channel.close()
            if self.connection and not self.connection.is_closed:
                self.connection.close()
            logger.debug("Disconnected from RabbitMQ")
        except Exception as e:
            logger.error(f"Error disconnecting from RabbitMQ: {e}")
    
    def publish_plan_update(
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
            if not self._connect():
                logger.error("Cannot publish message - RabbitMQ connection failed")
                return False

            # Create message payload
            message = {
                "tenant_id": tenant_id,
                "subscription_id": subscription_id,
                "plan_id": plan_id,
                "action": action,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

            # Convert to JSON
            message_body = json.dumps(message)

            # Publish message
            self.channel.basic_publish(
                exchange=self.exchange,
                routing_key=self.plan_update_routing_key,
                body=message_body,
                properties=pika.BasicProperties(
                    content_type='application/json',
                    delivery_mode=2  # Make message persistent
                )
            )

            logger.info(
                f"Published plan update message for tenant {tenant_id} "
                f"with subscription {subscription_id} and plan {plan_id} (action: {action})"
            )
            return True

        except AMQPChannelError as e:
            logger.error(f"Channel error publishing message: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error publishing message: {e}")
            return False
        finally:
            self._disconnect()
    
    def publish_plan_switch(
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
            if not self._connect():
                logger.error("Cannot publish message - RabbitMQ connection failed")
                return False

            # Create message payload with both old and new plan
            message = {
                "tenant_id": tenant_id,
                "subscription_id": subscription_id,
                "plan_id": new_plan_id,  # The new plan becomes the current plan
                "old_plan_id": old_plan_id,
                "action": "plan_switched",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

            # Convert to JSON
            message_body = json.dumps(message)

            # Publish message
            self.channel.basic_publish(
                exchange=self.exchange,
                routing_key=self.plan_update_routing_key,
                body=message_body,
                properties=pika.BasicProperties(
                    content_type='application/json',
                    delivery_mode=2  # Make message persistent
                )
            )

            logger.info(
                f"Published plan switch message for tenant {tenant_id} "
                f"with subscription {subscription_id} from plan {old_plan_id} to {new_plan_id}"
            )
            return True

        except AMQPChannelError as e:
            logger.error(f"Channel error publishing message: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error publishing message: {e}")
            return False
        finally:
            self._disconnect()
    
    def publish_logo_event(
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
            if not self._connect():
                logger.error("Cannot publish message - RabbitMQ connection failed")
                return False
            
            # Create message payload with comprehensive schema
            message = {
                "event_type": event_type,
                "tenant_id": tenant_id,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "data": logo_data or {}
            }
            
            # Convert to JSON
            message_body = json.dumps(message)
            
            # Publish message to logo-specific routing key
            self.channel.basic_publish(
                exchange=self.exchange,
                routing_key=self.logo_update_routing_key,
                body=message_body,
                properties=pika.BasicProperties(
                    content_type='application/json',
                    delivery_mode=2,  # Make message persistent
                    headers={
                        "event_type": event_type,
                        "tenant_id": tenant_id
                    }
                )
            )
            
            logger.info(
                f"Published logo event '{event_type}' for tenant {tenant_id}"
            )
            return True
            
        except AMQPChannelError as e:
            logger.error(f"Channel error publishing logo event message: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error publishing logo event message: {e}")
            return False
        finally:
            self._disconnect()
    
    def publish_logo_uploaded(
        self,
        tenant_id: str,
        logo_url: str
    ) -> bool:
        """Publish logo uploaded event"""
        logo_data = {
            "logo_url": logo_url
        }
        return self.publish_logo_event(tenant_id, "logo_uploaded", logo_data)
    
    def publish_logo_deleted(self, tenant_id: str) -> bool:
        """Publish logo deleted event"""
        return self.publish_logo_event(tenant_id, "logo_deleted")
    
    def publish_logo_updated(
        self,
        tenant_id: str,
        logo_url: str
    ) -> bool:
        """Publish logo updated event (for backwards compatibility)"""
        return self.publish_logo_uploaded(tenant_id, logo_url)
    
    def health_check(self) -> bool:
        """Check if RabbitMQ is accessible"""
        try:
            connected = self._connect()
            if connected:
                self._disconnect()
            return connected
        except Exception:
            return False


# Create a singleton instance
rabbitmq_service = RabbitMQService()