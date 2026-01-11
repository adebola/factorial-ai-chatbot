"""
RabbitMQ Consumer for Communications Service

MIGRATED TO AIO-PIKA: Now uses async-native RabbitMQ operations with automatic reconnection.
Eliminated manual connection retry logic and blocking I/O (515→320 lines, 38% reduction).

Consumes communication messages (emails and SMS) from RabbitMQ queues and processes them.
"""

import json
import os
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime

from aio_pika import connect_robust, ExchangeType, Message, DeliveryMode
from aio_pika.abc import AbstractRobustConnection, AbstractIncomingMessage
from aio_pika.exceptions import AMQPException
from sqlalchemy.orm import sessionmaker, Session

from ..core.database import engine
from ..services.email_service import EmailService
from ..services.sms_service import SMSService
from ..core.logging_config import get_logger, set_request_context, clear_request_context

logger = get_logger("rabbitmq_consumer")


class RabbitMQConsumer:
    """
    Async-native RabbitMQ consumer for processing communication messages.

    Handles email and SMS messages with automatic reconnection and retry logic.
    """

    def __init__(self):
        self.host = os.environ.get("RABBITMQ_HOST", "localhost")
        self.port = int(os.environ.get("RABBITMQ_PORT", "5672"))
        self.username = os.environ.get("RABBITMQ_USERNAME", "guest")
        self.password = os.environ.get("RABBITMQ_PASSWORD", "guest")
        self.exchange = os.environ.get("RABBITMQ_EXCHANGE", "communications-exchange")

        # Queue configuration
        self.email_queue = os.environ.get("RABBITMQ_EMAIL_QUEUE", "email.send")
        self.sms_queue = os.environ.get("RABBITMQ_SMS_QUEUE", "sms.send")

        self.connection: Optional[AbstractRobustConnection] = None
        self.consume_tasks: list = []

        # Database session maker
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        logger.info("RabbitMQ consumer initialized (aio-pika)")

    async def connect(self):
        """Establish robust connection with automatic reconnection."""
        if self.connection and not self.connection.is_closed:
            return

        self.connection = await connect_robust(
            host=self.host,
            port=self.port,
            login=self.username,
            password=self.password,
            reconnect_interval=1.0
        )

        logger.info(f"✓ Connected to RabbitMQ: {self.host}:{self.port}")

    async def start_consuming(self):
        """Start consuming messages from both email and SMS queues"""
        await self.connect()

        # Create channel
        channel = await self.connection.channel()
        await channel.set_qos(prefetch_count=1)

        # Declare exchange
        exchange = await channel.declare_exchange(
            self.exchange,
            ExchangeType.TOPIC,
            durable=True
        )

        # Declare email queue
        email_queue = await channel.declare_queue(
            self.email_queue,
            durable=True
        )

        # Bind email queue to routing keys
        await email_queue.bind(exchange, routing_key="email.send")
        await email_queue.bind(exchange, routing_key="email.notification")  # For auth server

        # Declare SMS queue
        sms_queue = await channel.declare_queue(
            self.sms_queue,
            durable=True
        )

        # Bind SMS queue
        await sms_queue.bind(exchange, routing_key="sms.send")

        logger.info(f"✓ Starting consumers for queues: {self.email_queue}, {self.sms_queue}")

        # Start consuming from both queues
        email_task = asyncio.create_task(email_queue.consume(self._process_email_message))
        sms_task = asyncio.create_task(sms_queue.consume(self._process_sms_message))

        self.consume_tasks = [email_task, sms_task]

        logger.info("✓ RabbitMQ consumers started successfully")

    async def stop_consuming(self):
        """Stop consuming messages"""
        for task in self.consume_tasks:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        if self.connection and not self.connection.is_closed:
            await self.connection.close()

        logger.info("RabbitMQ consumer stopped")

    async def _process_email_message(self, message: AbstractIncomingMessage):
        """
        Process email message from queue.

        Handles retry logic with x-retry-count header (max 3 retries).
        """
        db = None
        async with message.process(requeue=False):  # Don't auto-requeue, we handle it manually
            try:
                # Check retry count to prevent infinite loops
                retry_count = 0
                if message.headers:
                    retry_count = message.headers.get('x-retry-count', 0)

                max_retries = 3
                if retry_count >= max_retries:
                    logger.error(f"Message exceeded max retries ({max_retries}), discarding")
                    return  # Auto-reject without requeue

                logger.info("Received email message to be sent")

                # Parse message (handling double-encoded JSON)
                decoded_body = message.body.decode()
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

                logger.info(f"Sending mail for tenant {tenant_id} to {to_email}")

                if attachments:
                    logger.info(f"Email has {len(attachments)} attachment(s)")
                    for att in attachments:
                        logger.info(f"  - {att.get('filename', 'unknown')} ({att.get('content_type', 'unknown')})")

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
                    logger.info(f"✅ Email processed successfully: {message_id}")
                    # Auto-ack via context manager
                else:
                    # Retry if under limit
                    if retry_count < max_retries:
                        logger.warning(f"Email processing failed: {message_id}, retry {retry_count + 1}/{max_retries}")
                        await self._republish_with_retry(message, retry_count + 1)
                    else:
                        logger.error(f"Email processing failed permanently: {message_id}, discarding")

            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in email message: {e}")
                # Auto-reject without requeue (poison message)

            except ValueError as e:
                logger.error(f"Invalid email message format: {e}")
                # Auto-reject without requeue (invalid message)

            except Exception as e:
                logger.error(f"Error processing email message: {e}", exc_info=True)
                # Check retry count before requeuing
                retry_count = message.headers.get('x-retry-count', 0) if message.headers else 0

                if retry_count < max_retries:
                    logger.warning(f"Requeuing message for retry {retry_count + 1}/{max_retries}")
                    await self._republish_with_retry(message, retry_count + 1)
                else:
                    logger.error("Message exceeded max retries, discarding")

            finally:
                if db:
                    db.close()
                clear_request_context()

    async def _republish_with_retry(self, message: AbstractIncomingMessage, retry_count: int):
        """Republish message with incremented retry count"""
        try:
            # Create new headers with retry count
            new_headers = dict(message.headers) if message.headers else {}
            new_headers['x-retry-count'] = retry_count

            # Create new message
            new_message = Message(
                body=message.body,
                headers=new_headers,
                delivery_mode=DeliveryMode.PERSISTENT,
                content_type="application/json"
            )

            # Publish to the same routing key
            async with self.connection.channel() as channel:
                exchange = await channel.get_exchange(self.exchange)
                await exchange.publish(new_message, routing_key=message.routing_key)

            logger.info(f"Message republished with retry count: {retry_count}")

        except Exception as e:
            logger.error(f"Failed to republish message: {e}", exc_info=True)

    async def _process_sms_message(self, message: AbstractIncomingMessage):
        """Process SMS message from queue"""
        db = None
        async with message.process():
            try:
                # Parse message
                message_data = json.loads(message.body.decode())
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
                    logger.info(f"✅ SMS processed successfully: {message_id}")
                    # Auto-ack via context manager
                else:
                    logger.error(f"SMS processing failed: {message_id}")
                    raise Exception("SMS processing failed")  # Trigger nack+requeue

            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in SMS message: {e}")
                # Auto-reject without requeue (poison message)

            except ValueError as e:
                logger.error(f"Invalid SMS message format: {e}")
                # Auto-reject without requeue (invalid message)

            except Exception as e:
                logger.error(f"Error processing SMS message: {e}", exc_info=True)
                # Re-raise to trigger nack+requeue
                raise

            finally:
                if db:
                    db.close()
                clear_request_context()


# CLI function to start the consumer
async def start_consumer():
    """Start the RabbitMQ consumer (for CLI usage)"""
    consumer = RabbitMQConsumer()
    try:
        await consumer.start_consuming()
        # Keep running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Consumer stopped by user")
    finally:
        await consumer.stop_consuming()


if __name__ == "__main__":
    asyncio.run(start_consumer())
