"""Publishes fat audit events to the audit.events RabbitMQ exchange.

Usage:
    from .audit_publisher import audit_publisher
    await audit_publisher.publish(
        action_type="document.uploaded",
        tier="data",
        resource_type="document",
        resource_id="uuid",
        after_state={"filename": "report.pdf"},
    )

The publisher auto-extracts trace_id from OTel context and actor info
from the request_context (set by middleware or passed explicitly).
"""
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import aio_pika
from aio_pika import connect_robust, ExchangeType, Message
from aio_pika.abc import DeliveryMode

EXCHANGE_NAME = "audit.events"


class AuditPublisher:
    def __init__(self):
        self._connection = None
        self._channel = None
        self._exchange = None

    async def connect(self):
        if self._connection and not self._connection.is_closed:
            return

        host = os.environ.get("RABBITMQ_HOST", "localhost")
        port = int(os.environ.get("RABBITMQ_PORT", "5672"))
        user = os.environ.get("RABBITMQ_USER", "admin")
        password = os.environ.get("RABBITMQ_PASSWORD", "admin")
        vhost = os.environ.get("RABBITMQ_VHOST", "/")

        self._connection = await connect_robust(
            host=host, port=port, login=user, password=password,
            virtualhost=vhost, reconnect_interval=1.0
        )
        self._channel = await self._connection.channel()
        self._exchange = await self._channel.declare_exchange(
            EXCHANGE_NAME, ExchangeType.TOPIC, durable=True
        )

    async def publish(
        self,
        action_type: str,
        tier: str,
        source_service: str,
        tenant_id: str,
        actor_user_id: Optional[str] = None,
        actor_email: Optional[str] = None,
        actor_type: str = "user",
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        before_state: Optional[dict] = None,
        after_state: Optional[dict] = None,
        event_metadata: Optional[dict] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ):
        """Publish a fat audit event."""
        if not self._exchange:
            try:
                await self.connect()
            except Exception:
                return  # Fail silently — audit should not break business logic

        # Get trace context from OTel
        trace_id = None
        span_id = None
        try:
            from .core.telemetry import get_current_trace_id, get_current_span_id
            trace_id = get_current_trace_id()
            span_id = get_current_span_id()
        except Exception:
            try:
                from ..core.telemetry import get_current_trace_id, get_current_span_id
                trace_id = get_current_trace_id()
                span_id = get_current_span_id()
            except Exception:
                pass

        event = {
            "event_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "actor_user_id": actor_user_id,
            "actor_email": actor_email,
            "actor_type": actor_type,
            "action_type": action_type,
            "tier": tier,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "source_service": source_service,
            "trace_id": trace_id,
            "span_id": span_id,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "before_state": before_state,
            "after_state": after_state,
            "event_metadata": event_metadata,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            message = Message(
                body=json.dumps(event, default=str).encode(),
                delivery_mode=DeliveryMode.PERSISTENT,
                content_type="application/json",
            )
            await self._exchange.publish(message, routing_key=action_type)
        except Exception:
            pass  # Fail silently

    async def close(self):
        if self._connection and not self._connection.is_closed:
            await self._connection.close()


audit_publisher = AuditPublisher()

