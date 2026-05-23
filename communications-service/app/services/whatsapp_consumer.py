"""RabbitMQ consumer that processes inbound WhatsApp messages.

Listens on the `whatsapp.events` topic exchange (routing key
`whatsapp.message.process`), looks up the persisted inbound row, calls the
chat-service generate endpoint via WhatsAppService.handle_incoming_message,
then sends the AI reply back through Twilio.

Idempotency: WhatsAppService.handle_incoming_message skips rows where
`chat_session_id` is already populated (the marker we set after a successful
reply), so a requeued message will not produce a duplicate AI response.
"""
import json
import os
from typing import Optional, Tuple

import aio_pika
from aio_pika import ExchangeType, connect_robust

from ..core.database import SessionLocal
from ..core.logging_config import get_logger
from .audit_publisher import audit_publisher
from .whatsapp_service import WhatsAppService


EXCHANGE_NAME = "whatsapp.events"
QUEUE_NAME = "whatsapp.process"
ROUTING_KEY = "whatsapp.message.process"

logger = get_logger("whatsapp_consumer")


class WhatsAppConsumer:
    def __init__(self):
        self.connection: Optional[aio_pika.RobustConnection] = None
        self.channel: Optional[aio_pika.RobustChannel] = None

    async def connect(self) -> None:
        host = os.environ.get("RABBITMQ_HOST", "localhost")
        port = int(os.environ.get("RABBITMQ_PORT", "5672"))
        user = os.environ.get("RABBITMQ_USERNAME", "admin")
        password = os.environ.get("RABBITMQ_PASSWORD", "admin")
        vhost = os.environ.get("RABBITMQ_VHOST", "/")

        self.connection = await connect_robust(
            host=host, port=port, login=user, password=password,
            virtualhost=vhost, reconnect_interval=1.0,
        )
        self.channel = await self.connection.channel()
        await self.channel.set_qos(prefetch_count=5)

        exchange = await self.channel.declare_exchange(
            EXCHANGE_NAME, ExchangeType.TOPIC, durable=True,
        )
        queue = await self.channel.declare_queue(QUEUE_NAME, durable=True)
        await queue.bind(exchange, routing_key=ROUTING_KEY)

        logger.info(f"WhatsApp consumer connected — exchange={EXCHANGE_NAME}, queue={QUEUE_NAME}")

    async def start_consuming(self) -> None:
        if not self.channel:
            await self.connect()
        queue = await self.channel.declare_queue(QUEUE_NAME, durable=True)
        await queue.consume(self._process_message)
        logger.info("WhatsApp consumer started consuming")

    async def _process_message(self, message: aio_pika.IncomingMessage) -> None:
        async with message.process():
            try:
                event = json.loads(message.body.decode())
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                logger.error(f"Malformed WhatsApp event, discarding: {exc}")
                return

            inbound_message_id = event.get("inbound_message_id")
            tenant_id = event.get("tenant_id")
            if not inbound_message_id or not tenant_id:
                logger.warning(f"WhatsApp event missing required fields, discarding: {event}")
                return

            try:
                outbound_id = self._handle(inbound_message_id)
            except Exception as exc:
                # Raising re-queues the message; the idempotency guard in
                # handle_incoming_message will skip on the next attempt if we
                # had already sent a reply.
                logger.error(
                    f"Failed to process WhatsApp inbound {inbound_message_id}: {exc}",
                    extra={"tenant_id": tenant_id},
                )
                raise

            if outbound_id:
                try:
                    await audit_publisher.publish(
                        action_type="whatsapp.message.sent",
                        tier="data",
                        source_service="communications-service",
                        tenant_id=tenant_id,
                        actor_type="system",
                        resource_type="whatsapp_message",
                        resource_id=outbound_id,
                        event_metadata={
                            "inbound_message_id": inbound_message_id,
                            "wa_id": event.get("wa_id"),
                        },
                    )
                except Exception:
                    pass

    def _handle(self, inbound_message_id: str) -> Optional[str]:
        """Return the outbound WhatsAppMessage id on success, None otherwise."""
        db = SessionLocal()
        try:
            service = WhatsAppService(db)
            return service.handle_incoming_message(inbound_message_id)
        finally:
            db.close()

    async def stop(self) -> None:
        if self.connection and not self.connection.is_closed:
            await self.connection.close()
            logger.info("WhatsApp consumer connection closed")


whatsapp_consumer = WhatsAppConsumer()
