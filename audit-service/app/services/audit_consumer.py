"""RabbitMQ consumer for audit events from all services.

Listens on audit.events exchange, persists to audit_events table.
Idempotency enforced via event_id unique constraint.
"""
import json
import os
from datetime import datetime, timezone

import aio_pika
from aio_pika import connect_robust, ExchangeType, Message
from sqlalchemy.exc import IntegrityError

from ..core.database import SessionLocal
from ..core.logging_config import get_logger
from ..models.audit_event import AuditEvent

logger = get_logger("audit_consumer")

EXCHANGE_NAME = "audit.events"
QUEUE_NAME = "audit.event.store"


class AuditEventConsumer:
    def __init__(self):
        self.connection = None
        self.channel = None

    async def connect(self):
        host = os.environ.get("RABBITMQ_HOST", "localhost")
        port = int(os.environ.get("RABBITMQ_PORT", "5672"))
        user = os.environ.get("RABBITMQ_USER", "admin")
        password = os.environ.get("RABBITMQ_PASSWORD", "admin")
        vhost = os.environ.get("RABBITMQ_VHOST", "/")

        self.connection = await connect_robust(
            host=host, port=port, login=user, password=password,
            virtualhost=vhost, reconnect_interval=1.0
        )
        self.channel = await self.connection.channel()
        await self.channel.set_qos(prefetch_count=10)

        # Declare exchange and queue
        exchange = await self.channel.declare_exchange(
            EXCHANGE_NAME, ExchangeType.TOPIC, durable=True
        )
        queue = await self.channel.declare_queue(QUEUE_NAME, durable=True)
        await queue.bind(exchange, routing_key="#")  # Receive all events

        logger.info(f"Audit consumer connected — exchange={EXCHANGE_NAME}, queue={QUEUE_NAME}")

    async def start_consuming(self):
        queue = await self.channel.declare_queue(QUEUE_NAME, durable=True)
        await queue.consume(self._process_message)
        logger.info("Audit consumer started consuming")

    async def _process_message(self, message: aio_pika.IncomingMessage):
        logger.info(f"Processing Message : {message}")

        async with message.process():
            try:
                event = json.loads(message.body.decode())
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.error(f"Malformed audit event, discarding: {e}")
                return  # ack and discard

            event_id = event.get("event_id")
            if not event_id:
                logger.warning("Audit event missing event_id, discarding")
                return

            action_type = event.get("action_type")
            if not action_type:
                logger.warning(f"Audit event {event_id} missing action_type, discarding")
                return

            try:
                self._persist_event(event)
                logger.debug(f"Audit event persisted: {event_id} ({action_type})")
            except IntegrityError:
                # Duplicate event_id — already processed, skip
                logger.debug(f"Duplicate audit event {event_id}, skipping")
            except Exception as e:
                logger.error(f"Failed to persist audit event {event_id}: {e}")
                raise  # nack + requeue

    def _persist_event(self, event: dict):
        db = SessionLocal()
        try:
            occurred_at = event.get("occurred_at")
            if isinstance(occurred_at, str):
                try:
                    occurred_at = datetime.fromisoformat(occurred_at)
                except ValueError:
                    occurred_at = datetime.now(timezone.utc)
            elif not occurred_at:
                occurred_at = datetime.now(timezone.utc)

            audit_event = AuditEvent(
                event_id=event["event_id"],
                tenant_id=event.get("tenant_id", "unknown"),
                actor_user_id=event.get("actor_user_id"),
                actor_email=event.get("actor_email"),
                actor_type=event.get("actor_type", "system"),
                action_type=event["action_type"],
                tier=event.get("tier", "data"),
                resource_type=event.get("resource_type"),
                resource_id=event.get("resource_id"),
                source_service=event.get("source_service", "unknown"),
                trace_id=event.get("trace_id"),
                span_id=event.get("span_id"),
                ip_address=event.get("ip_address"),
                user_agent=event.get("user_agent"),
                before_state=event.get("before_state"),
                after_state=event.get("after_state"),
                event_metadata=event.get("event_metadata"),
                occurred_at=occurred_at,
                retention_days=event.get("retention_days"),
            )
            db.add(audit_event)
            db.commit()
        except IntegrityError:
            db.rollback()
            raise
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    async def stop(self):
        if self.connection and not self.connection.is_closed:
            await self.connection.close()
            logger.info("Audit consumer connection closed")


audit_consumer = AuditEventConsumer()
