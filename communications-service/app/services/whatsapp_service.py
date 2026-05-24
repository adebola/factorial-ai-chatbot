"""WhatsApp messaging service.

Orchestrates the per-tenant Twilio WhatsApp flow:
- Inbound webhook → record → publish to RabbitMQ → consumer → call chat-service → send reply
- Outbound delivery-status webhook → update existing row

Each tenant brings their own Twilio Account SID + Auth Token, so providers are
instantiated per-call from TenantSettings rather than from process-level env
vars.
"""
import os
from abc import ABC
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.logging_config import get_logger, log_message_failed, log_message_sent
from ..models.communications import (
    DeliveryLog,
    MessageStatus,
    MessageType,
    TenantSettings,
    WhatsAppMessage,
    WhatsAppPhoneMapping,
)
from .whatsapp_provider import (
    MockWhatsAppProvider,
    TwilioWhatsAppProvider,
    WhatsAppProvider,
)


WHATSAPP_PREFIX = "whatsapp:"

# Twilio rejects WhatsApp message bodies > 1600 chars (error 21617). This is
# the hard ceiling we must never cross; bodies sent must be <= this.
WHATSAPP_TWILIO_LIMIT = 1600
# Per-chunk size budget — leaves ~100 chars headroom for the "(i/N) "
# counter prefix and any future provider-side overhead.
WHATSAPP_MAX_BODY = 1500
# Hard cap on chunks so a runaway model output can't fan out 50 messages.
WHATSAPP_MAX_CHUNKS = 5


def _strip_whatsapp_prefix(phone: str) -> str:
    """Normalise a 'whatsapp:+E164' value back to '+E164' for storage / lookup."""
    if phone and phone.startswith(WHATSAPP_PREFIX):
        return phone[len(WHATSAPP_PREFIX):]
    return phone


def _chunk_for_whatsapp(
    text: str,
    max_len: int = WHATSAPP_MAX_BODY,
    max_chunks: int = WHATSAPP_MAX_CHUNKS,
) -> list:
    """Split `text` into ≤ max_chunks pieces, each ≤ max_len chars, breaking
    at safe boundaries: paragraph (\\n\\n), then line (\\n), then sentence
    ('. '), then space, falling back to a hard cut.

    If the text would need more than `max_chunks` chunks, the last chunk is
    a hard truncation and an ellipsis is appended so the recipient sees that
    the reply was cut off.
    """
    if not text:
        return [""]
    if len(text) <= max_len:
        return [text]

    chunks: list = []
    remaining = text.strip()
    while remaining and len(chunks) < max_chunks:
        if len(remaining) <= max_len:
            chunks.append(remaining)
            remaining = ""
            break

        window = remaining[:max_len]
        # Try increasingly-loose breakpoints; require at least max_len/2 of
        # content to avoid producing tiny dribbles.
        floor = max_len // 2
        cut = window.rfind("\n\n")
        if cut < floor:
            cut = window.rfind("\n")
        if cut < floor:
            sent = window.rfind(". ")
            cut = sent + 1 if sent >= floor else -1
        if cut < floor:
            cut = window.rfind(" ")
        if cut <= 0:
            cut = max_len  # hard cut

        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()

    if remaining:
        # We hit max_chunks but still have text left — truncate the last
        # chunk to signal there's more.
        last = chunks[-1].rstrip()
        suffix = " …(message truncated)"
        if len(last) + len(suffix) > max_len:
            last = last[: max_len - len(suffix)].rstrip()
        chunks[-1] = last + suffix

    return chunks


class WhatsAppServiceError(Exception):
    """Base exception for WhatsApp service errors."""


class TenantNotConfiguredError(WhatsAppServiceError):
    """The tenant has not completed /admin/whatsapp/setup."""


class WhatsAppRateLimitExceeded(WhatsAppServiceError):
    """The tenant has hit its daily outbound WhatsApp message cap."""


class WhatsAppService:
    """Service for WhatsApp messaging (per-tenant Twilio credentials)."""

    def __init__(self, db: Session):
        self.db = db
        self.logger = get_logger("whatsapp_service")
        # Process-level provider selector ('twilio' or 'mock'). Tenant credentials
        # are loaded per-call regardless — this only chooses which class to
        # instantiate.
        self.provider_name = os.environ.get("WHATSAPP_PROVIDER", "mock").lower()

    # ----- Provider construction -----

    def _status_callback_url(self) -> Optional[str]:
        """Return the URL Twilio should POST delivery-status updates to.

        Priority:
          1. `WHATSAPP_STATUS_CALLBACK_URL` env var (explicit, full URL).
          2. `PUBLIC_BASE_URL` env var + the standard status webhook path
             (`/api/v1/whatsapp/webhooks/twilio/status`).
          3. None — fall back to whatever default callback (if any) the tenant
             has configured on the number in the Twilio Console.

        Both env vars are optional; in dev with `WHATSAPP_PROVIDER=mock` the
        return value is irrelevant to message flow.
        """
        explicit = os.environ.get("WHATSAPP_STATUS_CALLBACK_URL")
        if explicit:
            return explicit.strip() or None
        public_base = os.environ.get("PUBLIC_BASE_URL")
        if public_base:
            return f"{public_base.rstrip('/')}/api/v1/whatsapp/webhooks/twilio/status"
        return None

    def _make_provider(self, account_sid: str, auth_token: str) -> WhatsAppProvider:
        """Instantiate a provider with the given tenant's credentials."""
        if self.provider_name == "twilio":
            return TwilioWhatsAppProvider(account_sid=account_sid, auth_token=auth_token)
        if self.provider_name == "mock":
            return MockWhatsAppProvider(account_sid=account_sid, auth_token=auth_token)
        raise ValueError(f"Unsupported WHATSAPP_PROVIDER: {self.provider_name}")

    def _load_tenant_settings(self, tenant_id: str) -> TenantSettings:
        """Load tenant settings; raises if WhatsApp is not configured."""
        settings = (
            self.db.query(TenantSettings)
            .filter(TenantSettings.tenant_id == tenant_id)
            .first()
        )
        if not settings or not settings.whatsapp_enabled:
            raise TenantNotConfiguredError(
                f"WhatsApp is not enabled for tenant {tenant_id}"
            )
        if self.provider_name == "twilio" and not (
            settings.whatsapp_twilio_sid and settings.whatsapp_twilio_token
        ):
            raise TenantNotConfiguredError(
                f"Tenant {tenant_id} is missing Twilio credentials"
            )
        return settings

    # ----- Tenant routing -----

    def resolve_tenant_from_phone(self, business_phone: str) -> Optional[str]:
        """Map an inbound `To` phone number to a tenant_id via WhatsAppPhoneMapping."""
        normalised = _strip_whatsapp_prefix(business_phone)
        mapping = (
            self.db.query(WhatsAppPhoneMapping)
            .filter(WhatsAppPhoneMapping.business_phone_number == normalised)
            .first()
        )
        return mapping.tenant_id if mapping else None

    def get_tenant_auth_token(self, tenant_id: str) -> Optional[str]:
        """Return the tenant's Twilio Auth Token, used for HMAC verification."""
        settings = (
            self.db.query(TenantSettings)
            .filter(TenantSettings.tenant_id == tenant_id)
            .first()
        )
        return settings.whatsapp_twilio_token if settings else None

    # ----- Inbound persistence (called by webhook BEFORE publishing) -----

    def record_inbound(
        self,
        tenant_id: str,
        provider_message_id: str,
        from_phone: str,
        to_phone: str,
        message_body: str,
        wa_id: Optional[str] = None,
    ) -> Tuple[Optional[WhatsAppMessage], bool]:
        """Persist an inbound WhatsApp row.

        Returns:
            (record, is_new) — `is_new` is False if a row with the same
            provider_message_id already exists (idempotency).
        """
        existing = (
            self.db.query(WhatsAppMessage)
            .filter(WhatsAppMessage.provider_message_id == provider_message_id)
            .first()
        )
        if existing:
            return existing, False

        record = WhatsAppMessage(
            tenant_id=tenant_id,
            direction="inbound",
            wa_id=wa_id or _strip_whatsapp_prefix(from_phone),
            to_phone=_strip_whatsapp_prefix(to_phone),
            from_phone=_strip_whatsapp_prefix(from_phone),
            message=message_body,
            provider_message_id=provider_message_id,
            status=MessageStatus.DELIVERED.value,
            sent_at=datetime.utcnow(),
            delivered_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
        )
        self.db.add(record)
        try:
            self.db.commit()
        except IntegrityError:
            # Race: another worker won the UNIQUE constraint. Re-fetch.
            self.db.rollback()
            record = (
                self.db.query(WhatsAppMessage)
                .filter(WhatsAppMessage.provider_message_id == provider_message_id)
                .first()
            )
            return record, False
        self.db.refresh(record)
        return record, True

    # ----- Outbound send -----

    def send_whatsapp_message(
        self,
        tenant_id: str,
        to_phone: str,
        message: str,
        chat_session_id: Optional[str] = None,
        wa_id: Optional[str] = None,
    ) -> Tuple[str, bool]:
        """Send a WhatsApp message from the tenant's business number.

        Returns (whatsapp_message_id, success).
        """
        settings = self._load_tenant_settings(tenant_id)
        from_phone = settings.whatsapp_phone_number
        if not from_phone:
            raise TenantNotConfiguredError(
                f"Tenant {tenant_id} has no whatsapp_phone_number"
            )

        if not self._check_and_reset_daily_limit(settings):
            self.logger.warning(
                "WhatsApp daily limit exceeded; dropping outbound",
                extra={
                    "tenant_id": tenant_id,
                    "daily_limit": settings.daily_whatsapp_limit,
                    "sent_today": settings.whatsapp_sent_today,
                },
            )
            raise WhatsAppRateLimitExceeded(
                f"Tenant {tenant_id} has reached its daily WhatsApp limit "
                f"({settings.daily_whatsapp_limit} messages)"
            )

        record = WhatsAppMessage(
            tenant_id=tenant_id,
            direction="outbound",
            wa_id=wa_id or _strip_whatsapp_prefix(to_phone),
            chat_session_id=chat_session_id,
            to_phone=_strip_whatsapp_prefix(to_phone),
            from_phone=_strip_whatsapp_prefix(from_phone),
            message=message,
            status=MessageStatus.PENDING.value,
            created_at=datetime.utcnow(),
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)

        try:
            provider = self._make_provider(
                account_sid=settings.whatsapp_twilio_sid or "MOCK_SID",
                auth_token=settings.whatsapp_twilio_token or "MOCK_TOKEN",
            )
            provider_id, success, error_message = provider.send_whatsapp(
                to_phone=to_phone,
                from_phone=from_phone,
                message=message,
                status_callback=self._status_callback_url(),
            )

            if success:
                self._update_status(
                    record.id,
                    status=MessageStatus.SENT.value,
                    provider_message_id=provider_id,
                    sent_at=datetime.utcnow(),
                )
                self._increment_daily_counter(settings)
                self._log_delivery(
                    record.id, tenant_id, "sent",
                    {"provider_id": provider_id, "provider": provider.get_provider_name()},
                )
                log_message_sent(
                    message_type="whatsapp",
                    message_id=record.id,
                    tenant_id=tenant_id,
                    recipient=to_phone,
                    provider=provider.get_provider_name(),
                    message_length=len(message),
                )
                return record.id, True

            self._update_status(record.id, status=MessageStatus.FAILED.value, error_message=error_message)
            log_message_failed(
                message_type="whatsapp",
                message_id=record.id,
                tenant_id=tenant_id,
                recipient=to_phone,
                error=error_message or "Unknown WhatsApp provider error",
            )
            return record.id, False

        except Exception as exc:  # noqa: BLE001
            error_msg = f"Failed to send WhatsApp: {exc}"
            self._update_status(record.id, status=MessageStatus.FAILED.value, error_message=error_msg)
            log_message_failed(
                message_type="whatsapp",
                message_id=record.id,
                tenant_id=tenant_id,
                recipient=to_phone,
                error=error_msg,
            )
            return record.id, False

    # ----- Incoming-message orchestration (called from the consumer) -----

    def handle_incoming_message(self, inbound_message_id: str) -> Optional[str]:
        """Look up an inbound row, call chat-service for an AI reply, send it back.

        Returns the outbound WhatsAppMessage id on success, None on failure.
        """
        inbound = (
            self.db.query(WhatsAppMessage)
            .filter(
                WhatsAppMessage.id == inbound_message_id,
                WhatsAppMessage.direction == "inbound",
            )
            .first()
        )
        if not inbound:
            self.logger.warning(f"Inbound WhatsApp message {inbound_message_id} not found")
            return None

        # Idempotency: chat_session_id is populated only after a successful reply.
        # If it's set, this row has already been processed — skip on requeue.
        if inbound.chat_session_id:
            self.logger.info(
                f"Inbound {inbound_message_id} already processed (chat_session_id={inbound.chat_session_id}), skipping"
            )
            return None

        try:
            reply = self._call_chat_service(
                tenant_id=inbound.tenant_id,
                user_identifier=inbound.wa_id,
                message=inbound.message,
            )
        except Exception as exc:  # noqa: BLE001
            self.logger.error(
                f"chat-service call failed for {inbound_message_id}: {exc}",
                extra={"tenant_id": inbound.tenant_id},
            )
            return None

        reply_text = reply.get("content") or "I'm not able to respond right now."
        session_id = reply.get("session_id")

        chunks = _chunk_for_whatsapp(reply_text)
        total = len(chunks)
        first_outbound_id: Optional[str] = None
        any_success = False

        for index, chunk in enumerate(chunks):
            body = chunk if total == 1 else f"({index + 1}/{total}) {chunk}"
            try:
                outbound_id, success = self.send_whatsapp_message(
                    tenant_id=inbound.tenant_id,
                    to_phone=inbound.from_phone,
                    message=body,
                    chat_session_id=session_id,
                    wa_id=inbound.wa_id,
                )
            except WhatsAppRateLimitExceeded:
                self.logger.warning(
                    "Stopping multi-chunk reply: daily WhatsApp limit exceeded",
                    extra={
                        "tenant_id": inbound.tenant_id,
                        "inbound_message_id": inbound_message_id,
                        "chunks_sent": index,
                        "chunks_total": total,
                    },
                )
                break
            except TenantNotConfiguredError as exc:
                self.logger.warning(
                    f"Cannot reply — tenant misconfigured: {exc}",
                    extra={"tenant_id": inbound.tenant_id, "inbound_message_id": inbound_message_id},
                )
                return None

            if success:
                any_success = True
                if first_outbound_id is None:
                    first_outbound_id = outbound_id
                # After the first successful send, mark the inbound row so a
                # requeue (e.g. RabbitMQ redelivery) doesn't replay chunks
                # and produce duplicate replies.
                if inbound.chat_session_id is None:
                    inbound.chat_session_id = session_id
                    self.db.commit()
            else:
                # Stop sending subsequent chunks if one fails — sending part 3
                # without part 2 is worse than just stopping.
                self.logger.warning(
                    "Stopping multi-chunk reply: chunk failed at provider",
                    extra={
                        "tenant_id": inbound.tenant_id,
                        "inbound_message_id": inbound_message_id,
                        "failed_chunk": index + 1,
                        "chunks_total": total,
                    },
                )
                break

        return first_outbound_id if any_success else None

    def _call_chat_service(
        self,
        tenant_id: str,
        user_identifier: str,
        message: str,
    ) -> Dict[str, Any]:
        """POST to chat-service's internal generate endpoint."""
        base_url = os.environ.get("CHAT_SERVICE_URL", "http://localhost:8000")
        token = os.environ.get("INTERNAL_SERVICE_TOKEN")
        if not token:
            raise WhatsAppServiceError("INTERNAL_SERVICE_TOKEN env var is not set")

        url = f"{base_url.rstrip('/')}/api/v1/internal/chat/generate"
        payload = {
            "tenant_id": tenant_id,
            "user_identifier": user_identifier,
            "message": message,
        }
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                url,
                json=payload,
                headers={"X-Internal-Service-Token": token},
            )
            response.raise_for_status()
            return response.json()

    # ----- Delivery-status webhook -----

    def handle_delivery_status(self, twilio_payload: Dict[str, Any]) -> bool:
        """Update an outbound row from a Twilio status callback.

        Twilio sends MessageSid + MessageStatus on every state transition.
        """
        provider_message_id = twilio_payload.get("MessageSid")
        twilio_status = (twilio_payload.get("MessageStatus") or "").lower()
        if not provider_message_id:
            self.logger.warning("Status webhook missing MessageSid")
            return False

        record = (
            self.db.query(WhatsAppMessage)
            .filter(WhatsAppMessage.provider_message_id == provider_message_id)
            .first()
        )
        if not record:
            self.logger.info(f"No WhatsApp row for MessageSid {provider_message_id}")
            return False

        # Map Twilio status → our MessageStatus
        mapping = {
            "queued": MessageStatus.PENDING.value,
            "sending": MessageStatus.PENDING.value,
            "sent": MessageStatus.SENT.value,
            "delivered": MessageStatus.DELIVERED.value,
            "read": MessageStatus.OPENED.value,
            "failed": MessageStatus.FAILED.value,
            "undelivered": MessageStatus.FAILED.value,
        }
        new_status = mapping.get(twilio_status)
        if new_status:
            record.status = new_status
            if new_status == MessageStatus.DELIVERED.value:
                record.delivered_at = datetime.utcnow()
            if new_status == MessageStatus.FAILED.value:
                record.error_message = twilio_payload.get("ErrorMessage") or twilio_status
            self.db.commit()

        self._log_delivery(
            record.id,
            record.tenant_id,
            event_type=twilio_status,
            provider_response=twilio_payload,
        )
        return True

    # ----- Rate limiting -----

    def _check_and_reset_daily_limit(self, settings: TenantSettings) -> bool:
        """Return True if the tenant is under the daily outbound cap.

        Resets the shared `limit_reset_date` counter pair (sms + whatsapp) once
        per day, mirroring the SMS rate-limit behaviour in sms_service.py.
        """
        today = datetime.utcnow().date()
        if settings.limit_reset_date and settings.limit_reset_date.date() < today:
            settings.sms_sent_today = 0
            settings.whatsapp_sent_today = 0
            settings.limit_reset_date = datetime.utcnow()
            self.db.commit()

        limit = settings.daily_whatsapp_limit or 0
        if limit <= 0:
            # 0 or NULL means "unlimited" for this tenant. Negative values
            # would have been a misconfiguration; treat as unlimited too.
            return True
        return (settings.whatsapp_sent_today or 0) < limit

    def _increment_daily_counter(self, settings: TenantSettings) -> None:
        settings.whatsapp_sent_today = (settings.whatsapp_sent_today or 0) + 1
        self.db.commit()

    # ----- Helpers -----

    def _update_status(
        self,
        message_id: str,
        status: str,
        provider_message_id: Optional[str] = None,
        sent_at: Optional[datetime] = None,
        delivered_at: Optional[datetime] = None,
        error_message: Optional[str] = None,
    ) -> None:
        record = self.db.query(WhatsAppMessage).filter(WhatsAppMessage.id == message_id).first()
        if not record:
            return
        record.status = status
        if provider_message_id:
            record.provider_message_id = provider_message_id
        if sent_at:
            record.sent_at = sent_at
        if delivered_at:
            record.delivered_at = delivered_at
        if error_message:
            record.error_message = error_message
        self.db.commit()

    def _log_delivery(
        self,
        message_id: str,
        tenant_id: str,
        event_type: str,
        provider_response: Dict[str, Any],
    ) -> None:
        now = datetime.utcnow()
        entry = DeliveryLog(
            message_id=message_id,
            message_type=MessageType.WHATSAPP.value,
            tenant_id=tenant_id,
            event_type=event_type,
            provider_name=self.provider_name,
            provider_response=provider_response,
            occurred_at=now,
            created_at=now,
        )
        self.db.add(entry)
        self.db.commit()

    # ----- Read helpers (used by the messages list API) -----

    def get_message(self, message_id: str, tenant_id: str) -> Optional[WhatsAppMessage]:
        return (
            self.db.query(WhatsAppMessage)
            .filter(
                WhatsAppMessage.id == message_id,
                WhatsAppMessage.tenant_id == tenant_id,
            )
            .first()
        )

    def list_tenant_messages(
        self,
        tenant_id: str,
        skip: int = 0,
        limit: int = 50,
        status: Optional[str] = None,
        direction: Optional[str] = None,
    ) -> List[WhatsAppMessage]:
        query = self.db.query(WhatsAppMessage).filter(WhatsAppMessage.tenant_id == tenant_id)
        if status:
            query = query.filter(WhatsAppMessage.status == status)
        if direction:
            query = query.filter(WhatsAppMessage.direction == direction)
        return (
            query.order_by(WhatsAppMessage.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
