import json
import os
import asyncio
from typing import Dict, Any, Callable
from datetime import datetime

import pika
from pika.exceptions import AMQPConnectionError, AMQPChannelError
from sqlalchemy.orm import sessionmaker, Session

from ..core.database import engine
from ..services.email_service import EmailService
from ..services.sms_service import SMSService
from ..core.logging_config import get_logger, set_request_context, clear_request_context

logger = get_logger("rabbitmq_consumer")


class RabbitMQConsumer:
    """RabbitMQ consumer for processing communication messages"""

    def __init__(self):
        self.host = os.environ.get("RABBITMQ_HOST", "localhost")
        self.port = int(os.environ.get("RABBITMQ_PORT", "5672"))
        self.username = os.environ.get("RABBITMQ_USERNAME", "guest")
        self.password = os.environ.get("RABBITMQ_PASSWORD", "guest")
        self.exchange = os.environ.get("RABBITMQ_EXCHANGE", "communications-exchange")

        # Queue configuration
        self.email_queue = os.environ.get("RABBITMQ_EMAIL_QUEUE", "email.send")
        self.sms_queue = os.environ.get("RABBITMQ_SMS_QUEUE", "sms.send")

        self.connection = None
        self.channel = None

        # Database session maker
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def _connect(self) -> bool:
        """Establish connection to RabbitMQ"""
        try:
            if self.connection and not self.connection.is_closed:
                return True

            credentials = pika.PlainCredentials(self.username, self.password)
            parameters = pika.ConnectionParameters(
                host=self.host,
                port=self.port,
                credentials=credentials,
                heartbeat=600,
                blocked_connection_timeout=300
            )

            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()

            # Declare exchange
            self.channel.exchange_declare(
                exchange=self.exchange,
                exchange_type='topic',
                durable=True
            )

            # Declare queues
            self.channel.queue_declare(queue=self.email_queue, durable=True)
            self.channel.queue_declare(queue=self.sms_queue, durable=True)

            # Bind queues to exchange
            self.channel.queue_bind(
                exchange=self.exchange,
                queue=self.email_queue,
                routing_key="email.send"
            )

            # Also bind to email.notification routing key for the authorization server
            self.channel.queue_bind(
                exchange=self.exchange,
                queue=self.email_queue,
                routing_key="email.notification"
            )

            self.channel.queue_bind(
                exchange=self.exchange,
                queue=self.sms_queue,
                routing_key="sms.send"
            )

            # Set QoS to process one message at a time
            self.channel.basic_qos(prefetch_count=1)

            logger.info("Connected to RabbitMQ successfully")
            return True

        except AMQPConnectionError as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            return False

    def _disconnect(self):
        """Close RabbitMQ connection"""
        try:
            if self.channel and not self.channel.is_closed:
                self.channel.close()
            if self.connection and not self.connection.is_closed:
                self.connection.close()
            logger.info("Disconnected from RabbitMQ")
        except Exception as e:
            logger.error(f"Error disconnecting from RabbitMQ: {e}")

    def _process_email_message(self, ch, method, properties, body):
        """Process email message from queue"""
        db = None
        try:
            # Check retry count to prevent infinite loops
            retry_count = 0
            if hasattr(properties, 'headers') and properties.headers:
                retry_count = properties.headers.get('x-retry-count', 0)

            max_retries = 3  # Maximum number of retries
            if retry_count >= max_retries:
                logger.error(f"Message exceeded max retries ({max_retries}), discarding")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                return
            logger.info("received Email Message to be sent")
            # Parse message (handling double-encoded JSON)
            decoded_body = body.decode()
            message_data = json.loads(decoded_body)

            # If message_data is still a string, it was double-encoded
            if isinstance(message_data, str):
                message_data = json.loads(message_data)

            logger.info(f"Processing email message: {message_data.get('message_id', 'unknown')}")

            # Map field names from the authorization server format
            tenant_id = message_data.get("tenantId") or message_data.get("tenant_id")
            to_email = message_data.get("toEmail") or message_data.get("to_email")
            to_name = message_data.get("toName") or message_data.get("to_name")
            html_content = message_data.get("htmlContent") or message_data.get("html_content")
            text_content = message_data.get("textContent") or message_data.get("text_content")
            attachments = message_data.get("attachments")

            logger.info(f"Sending Mail for Tenant {tenant_id}")
            logger.info(f"Sending mail to {to_email}")

            if attachments:
                logger.info(f"Email has {len(attachments)} attachment(s)")
                for att in attachments:
                    logger.info(f"  - {att.get('filename', 'unknown')} ({att.get('content_type', 'unknown')})")
            # logger.info(f"Sending content {html_content}")

            # Set request context
            set_request_context(
                tenant_id=tenant_id,
                operation="queue_email_send",
                message_id=message_data.get("message_id")
            )

            # Validate required fields
            if not tenant_id:
                raise ValueError("Missing required field: tenantId")
            if not to_email:
                raise ValueError("Missing required field: toEmail")
            if not message_data.get("subject"):
                raise ValueError("Missing required field: subject")

            # Get database session
            db = self.SessionLocal()

            # Send email
            email_service = EmailService(db)
            message_id, success = email_service.send_email(
                tenant_id=tenant_id,
                to_email=to_email,
                subject=message_data["subject"],
                html_content=html_content,
                text_content=text_content,
                to_name=to_name,
                attachments=attachments,
                template_data=message_data.get("templateData") or message_data.get("template_data")
            )

            if success:
                # Acknowledge message
                ch.basic_ack(delivery_tag=method.delivery_tag)
                logger.info(f"Email processed successfully: {message_id}")
            else:
                # Increment retry count and requeue if under limit
                if retry_count < max_retries:
                    logger.warning(f"Email processing failed: {message_id}, retry {retry_count + 1}/{max_retries}")
                    # Republish with incremented retry count
                    self._republish_with_retry(ch, method, properties, body, retry_count + 1)
                    ch.basic_ack(delivery_tag=method.delivery_tag)  # Ack original message
                else:
                    logger.error(f"Email processing failed permanently: {message_id}, discarding")
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in email message: {e}")
            # Reject without requeue (poison message)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

        except ValueError as e:
            logger.error(f"Invalid email message format: {e}")
            # Reject without requeue (invalid message)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

        except Exception as e:
            logger.error(f"Error processing email message: {e}")
            # Check retry count before requeuing
            retry_count = 0
            if hasattr(properties, 'headers') and properties.headers:
                retry_count = properties.headers.get('x-retry-count', 0)

            max_retries = 3
            if retry_count < max_retries:
                logger.warning(f"Requeuing message for retry {retry_count + 1}/{max_retries}")
                self._republish_with_retry(ch, method, properties, body, retry_count + 1)
                ch.basic_ack(delivery_tag=method.delivery_tag)  # Ack original message
            else:
                logger.error(f"Message exceeded max retries, discarding")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

        finally:
            if db:
                db.close()
            clear_request_context()

    def _republish_with_retry(self, ch, method, properties, body, retry_count):
        """Republish message with incremented retry count"""
        try:
            # Create new properties with retry count header
            new_headers = properties.headers.copy() if properties.headers else {}
            new_headers['x-retry-count'] = retry_count

            new_properties = pika.BasicProperties(
                headers=new_headers,
                delivery_mode=2,  # Persistent
                content_type="application/json"
            )

            # Republish to the same queue
            ch.basic_publish(
                exchange=self.exchange,
                routing_key=method.routing_key,
                body=body,
                properties=new_properties
            )
            logger.info(f"Message republished with retry count: {retry_count}")

        except Exception as e:
            logger.error(f"Failed to republish message: {e}")

    def _process_sms_message(self, ch, method, properties, body):
        """Process SMS message from queue"""
        db = None
        try:
            # Parse message
            message_data = json.loads(body.decode())
            logger.info(f"Processing SMS message: {message_data.get('message_id', 'unknown')}")

            # Set request context
            set_request_context(
                tenant_id=message_data.get("tenant_id"),
                operation="queue_sms_send",
                message_id=message_data.get("message_id")
            )

            # Validate required fields
            required_fields = ["tenant_id", "to_phone", "message"]
            for field in required_fields:
                if field not in message_data:
                    raise ValueError(f"Missing required field: {field}")

            # Get database session
            db = self.SessionLocal()

            # Send SMS
            sms_service = SMSService(db)
            message_id, success = sms_service.send_sms(
                tenant_id=message_data["tenant_id"],
                to_phone=message_data["to_phone"],
                message=message_data["message"],
                from_phone=message_data.get("from_phone"),
                template_id=message_data.get("template_id"),
                template_data=message_data.get("template_data")
            )

            if success:
                # Acknowledge message
                ch.basic_ack(delivery_tag=method.delivery_tag)
                logger.info(f"SMS processed successfully: {message_id}")
            else:
                # Reject and requeue for retry
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                logger.error(f"SMS processing failed: {message_id}")

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in SMS message: {e}")
            # Reject without requeue (poison message)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

        except ValueError as e:
            logger.error(f"Invalid SMS message format: {e}")
            # Reject without requeue (invalid message)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

        except Exception as e:
            logger.error(f"Error processing SMS message: {e}")
            # Reject and requeue for retry
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

        finally:
            if db:
                db.close()
            clear_request_context()

    def start_consuming(self):
        """Start consuming messages from RabbitMQ"""
        retry_count = 0
        max_retries = 5
        retry_delay = 5

        while retry_count < max_retries:
            try:
                if not self._connect():
                    retry_count += 1
                    logger.error(f"Failed to connect to RabbitMQ (attempt {retry_count}/{max_retries})")
                    if retry_count >= max_retries:
                        logger.error("Maximum connection attempts reached. RabbitMQ consumer will not start.")
                        return
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    import time
                    time.sleep(retry_delay)
                    continue

                # Reset retry count on successful connection
                retry_count = 0

                # Set up consumers
                self.channel.basic_consume(
                    queue=self.email_queue,
                    on_message_callback=self._process_email_message
                )

                self.channel.basic_consume(
                    queue=self.sms_queue,
                    on_message_callback=self._process_sms_message
                )

                logger.info("Starting to consume messages...")
                self.channel.start_consuming()

            except KeyboardInterrupt:
                logger.info("Stopping consumer...")
                self.channel.stop_consuming()
                self._disconnect()
                break

            except AMQPConnectionError as e:
                retry_count += 1
                logger.error(f"Connection error: {e}")
                self._disconnect()
                if retry_count >= max_retries:
                    logger.error("Maximum connection attempts reached. RabbitMQ consumer stopped.")
                    break
                logger.info(f"Retrying in {retry_delay} seconds... (attempt {retry_count}/{max_retries})")
                import time
                time.sleep(retry_delay)

            except Exception as e:
                retry_count += 1
                logger.error(f"Unexpected error: {e}")
                self._disconnect()
                if retry_count >= max_retries:
                    logger.error("Maximum retry attempts reached. RabbitMQ consumer stopped.")
                    break
                logger.info(f"Retrying in {retry_delay} seconds... (attempt {retry_count}/{max_retries})")
                import time
                time.sleep(retry_delay)

        logger.warning("RabbitMQ consumer stopped. The service will continue without message queue functionality.")

    def stop_consuming(self):
        """Stop consuming messages"""
        try:
            if self.channel:
                self.channel.stop_consuming()
            self._disconnect()
        except Exception as e:
            logger.error(f"Error stopping consumer: {e}")


class RabbitMQPublisher:
    """RabbitMQ publisher for sending messages to queues"""

    def __init__(self):
        self.host = os.environ.get("RABBITMQ_HOST", "localhost")
        self.port = int(os.environ.get("RABBITMQ_PORT", "5672"))
        self.username = os.environ.get("RABBITMQ_USERNAME", "guest")
        self.password = os.environ.get("RABBITMQ_PASSWORD", "guest")
        self.exchange = os.environ.get("RABBITMQ_EXCHANGE", "communications-exchange")

        self.connection = None
        self.channel = None

    def _connect(self) -> bool:
        """Establish connection to RabbitMQ"""
        try:
            if self.connection and not self.connection.is_closed:
                return True

            credentials = pika.PlainCredentials(self.username, self.password)
            parameters = pika.ConnectionParameters(
                host=self.host,
                port=self.port,
                credentials=credentials,
                heartbeat=600,
                blocked_connection_timeout=300
            )

            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()

            # Declare exchange
            self.channel.exchange_declare(
                exchange=self.exchange,
                exchange_type='topic',
                durable=True
            )

            return True

        except AMQPConnectionError as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            return False

    def publish_email_message(self, message_data: Dict[str, Any]) -> bool:
        """Publish email message to queue"""
        try:
            if not self._connect():
                return False

            # Add timestamp
            message_data["queued_at"] = datetime.utcnow().isoformat()

            # Publish message
            self.channel.basic_publish(
                exchange=self.exchange,
                routing_key="email.send",
                body=json.dumps(message_data),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Make message persistent
                    content_type="application/json"
                )
            )

            logger.info(f"Email message published: {message_data.get('message_id', 'unknown')}")
            return True

        except Exception as e:
            logger.error(f"Failed to publish email message: {e}")
            return False

    def publish_sms_message(self, message_data: Dict[str, Any]) -> bool:
        """Publish SMS message to queue"""
        try:
            if not self._connect():
                return False

            # Add timestamp
            message_data["queued_at"] = datetime.utcnow().isoformat()

            # Publish message
            self.channel.basic_publish(
                exchange=self.exchange,
                routing_key="sms.send",
                body=json.dumps(message_data),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Make message persistent
                    content_type="application/json"
                )
            )

            logger.info(f"SMS message published: {message_data.get('message_id', 'unknown')}")
            return True

        except Exception as e:
            logger.error(f"Failed to publish SMS message: {e}")
            return False

    def close(self):
        """Close connection"""
        try:
            if self.channel and not self.channel.is_closed:
                self.channel.close()
            if self.connection and not self.connection.is_closed:
                self.connection.close()
        except Exception as e:
            logger.error(f"Error closing publisher connection: {e}")


# CLI function to start the consumer
def start_consumer():
    """Start the RabbitMQ consumer (for CLI usage)"""
    consumer = RabbitMQConsumer()
    try:
        consumer.start_consuming()
    except KeyboardInterrupt:
        logger.info("Consumer stopped by user")
    finally:
        consumer.stop_consuming()


if __name__ == "__main__":
    start_consumer()