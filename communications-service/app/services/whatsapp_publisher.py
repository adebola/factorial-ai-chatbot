"""Publishes WhatsApp message-processing events to RabbitMQ.

The inbound webhook ACKs Twilio fast (<1s) and publishes a small event
referencing the persisted WhatsAppMessage row. The consumer (Phase 6) then
calls chat-service and sends the reply asynchronously — outside the webhook
critical path.

Exchange: `whatsapp.events` (topic, durable)
Routing key: `whatsapp.message.process`
"""
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import aio_pika
from aio_pika import ExchangeType, Message, connect_robust
from aio_pika.abc import DeliveryMode

from ..core.logging_config import get_logger


EXCHANGE_NAME = "whatsapp.events"
ROUTING_KEY_PROCESS = "whatsapp.message.process"

logger = get_logger("whatsapp_publisher")


class WhatsAppPublisher:
    def __init__(self):
        self._connection: Optional[aio_pika.RobustConnection] = None
        self._channel: Optional[aio_pika.RobustChannel] = None
        self._exchange: Optional[aio_pika.RobustExchange] = None

    async def connect(self) -> None:
        if self._connection and not self._connection.is_closed:
            return

        host = os.environ.get("RABBITMQ_HOST", "localhost")
        port = int(os.environ.get("RABBITMQ_PORT", "5672"))
        user = os.environ.get("RABBITMQ_USERNAME", "admin")
        password = os.environ.get("RABBITMQ_PASSWORD", "admin")
        vhost = os.environ.get("RABBITMQ_VHOST", "/")

        self._connection = await connect_robust(
            host=host, port=port, login=user, password=password,
            virtualhost=vhost, reconnect_interval=1.0,
        )
        self._channel = await self._connection.channel()
        self._exchange = await self._channel.declare_exchange(
            EXCHANGE_NAME, ExchangeType.TOPIC, durable=True,
        )

    async def publish_message_process(
        self,
        tenant_id: str,
        inbound_message_id: str,
        provider_message_id: str,
        wa_id: Optional[str] = None,
    ) -> bool:
        """Publish a 'process this inbound message' event.

        Returns True on success. Logs and returns False on any failure — the
        webhook caller has already ACKed Twilio, so a publish failure is
        observable but not customer-facing on the inbound path.
        """
        if not self._exchange:
            try:
                await self.connect()
            except Exception as exc:  # noqa: BLE001
                logger.error(f"WhatsApp publisher could not connect to RabbitMQ: {exc}")
                return False

        event = {
            "event_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "inbound_message_id": inbound_message_id,
            "provider_message_id": provider_message_id,
            "wa_id": wa_id,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            message = Message(
                body=json.dumps(event, default=str).encode(),
                delivery_mode=DeliveryMode.PERSISTENT,
                content_type="application/json",
            )
            await self._exchange.publish(message, routing_key=ROUTING_KEY_PROCESS)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error(
                f"Failed to publish whatsapp.message.process event: {exc}",
                extra={"tenant_id": tenant_id, "inbound_message_id": inbound_message_id},
            )
            return False

    async def close(self) -> None:
        if self._connection and not self._connection.is_closed:
            await self._connection.close()


whatsapp_publisher = WhatsAppPublisher()
