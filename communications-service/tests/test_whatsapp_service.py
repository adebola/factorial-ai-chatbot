"""Unit tests for WhatsAppService.

Covers: tenant resolution, idempotency (UNIQUE provider_message_id),
multi-tenant isolation, rate limiting, mock-provider send path, and the
handle_incoming_message orchestrator with httpx + provider mocked.
"""
import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.models.communications import (
    MessageStatus,
    TenantSettings,
    WhatsAppMessage,
    WhatsAppPhoneMapping,
)
from app.services.whatsapp_service import (
    TenantNotConfiguredError,
    WhatsAppRateLimitExceeded,
    WhatsAppService,
    _strip_whatsapp_prefix,
)


TENANT_A = "tenant-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
TENANT_B = "tenant-bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
PHONE_A = "+14155238886"
PHONE_B = "+14155551234"


def _configure_tenant(
    db, tenant_id: str, phone: str,
    enabled: bool = True,
    sid: str = "ACtest_sid_1234567890abcdef",
    token: str = "tok_test_secret",
    daily_limit: int = 1000,
):
    """Seed TenantSettings + WhatsAppPhoneMapping for a tenant."""
    settings = TenantSettings(
        tenant_id=tenant_id,
        whatsapp_enabled=enabled,
        whatsapp_twilio_sid=sid if enabled else None,
        whatsapp_twilio_token=token if enabled else None,
        whatsapp_phone_number=phone if enabled else None,
        daily_whatsapp_limit=daily_limit,
        whatsapp_sent_today=0,
        limit_reset_date=datetime.utcnow(),
    )
    db.add(settings)
    if enabled:
        db.add(WhatsAppPhoneMapping(tenant_id=tenant_id, business_phone_number=phone))
    db.commit()
    return settings


class TestResolveTenant:
    def test_resolves_tenant_from_To_phone(self, db_session):
        _configure_tenant(db_session, TENANT_A, PHONE_A)
        service = WhatsAppService(db_session)

        assert service.resolve_tenant_from_phone(PHONE_A) == TENANT_A
        # Twilio-prefixed format also accepted
        assert service.resolve_tenant_from_phone(f"whatsapp:{PHONE_A}") == TENANT_A

    def test_returns_none_for_unknown_phone(self, db_session):
        service = WhatsAppService(db_session)
        assert service.resolve_tenant_from_phone("+19999999999") is None

    def test_returns_correct_tenant_when_multiple_exist(self, db_session):
        _configure_tenant(db_session, TENANT_A, PHONE_A)
        _configure_tenant(db_session, TENANT_B, "+14152223333")
        service = WhatsAppService(db_session)

        assert service.resolve_tenant_from_phone(PHONE_A) == TENANT_A
        assert service.resolve_tenant_from_phone("+14152223333") == TENANT_B


class TestRecordInbound:
    def test_persists_normalised_phone_numbers(self, db_session):
        _configure_tenant(db_session, TENANT_A, PHONE_A)
        service = WhatsAppService(db_session)

        record, is_new = service.record_inbound(
            tenant_id=TENANT_A,
            provider_message_id="SM_new_1",
            from_phone=f"whatsapp:{PHONE_B}",
            to_phone=f"whatsapp:{PHONE_A}",
            message_body="Hello bot",
        )
        assert is_new is True
        assert record.from_phone == PHONE_B   # 'whatsapp:' prefix stripped
        assert record.to_phone == PHONE_A
        assert record.direction == "inbound"
        assert record.status == MessageStatus.DELIVERED.value

    def test_idempotency_same_MessageSid_returns_existing_row(self, db_session):
        _configure_tenant(db_session, TENANT_A, PHONE_A)
        service = WhatsAppService(db_session)

        first, is_new_first = service.record_inbound(
            tenant_id=TENANT_A,
            provider_message_id="SM_dup",
            from_phone=PHONE_B, to_phone=PHONE_A, message_body="first",
        )
        second, is_new_second = service.record_inbound(
            tenant_id=TENANT_A,
            provider_message_id="SM_dup",
            from_phone=PHONE_B, to_phone=PHONE_A, message_body="should_not_overwrite",
        )

        assert is_new_first is True
        assert is_new_second is False
        assert first.id == second.id
        # Only one row exists for that SID
        all_rows = db_session.query(WhatsAppMessage).filter_by(provider_message_id="SM_dup").all()
        assert len(all_rows) == 1
        # First message body is preserved
        assert all_rows[0].message == "first"


class TestSendWhatsAppMessage:
    @pytest.fixture(autouse=True)
    def _force_mock_provider(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_PROVIDER", "mock")
        yield

    def test_send_requires_configured_tenant(self, db_session):
        service = WhatsAppService(db_session)
        with pytest.raises(TenantNotConfiguredError):
            service.send_whatsapp_message(
                tenant_id="unconfigured-tenant", to_phone=PHONE_B, message="hi",
            )

    def test_send_creates_outbound_row_and_marks_sent(self, db_session):
        _configure_tenant(db_session, TENANT_A, PHONE_A)
        service = WhatsAppService(db_session)

        outbound_id, success = service.send_whatsapp_message(
            tenant_id=TENANT_A, to_phone=PHONE_B, message="Reply from bot",
        )
        assert success is True

        row = db_session.query(WhatsAppMessage).filter_by(id=outbound_id).first()
        assert row is not None
        assert row.direction == "outbound"
        assert row.tenant_id == TENANT_A
        assert row.to_phone == PHONE_B
        assert row.from_phone == PHONE_A
        assert row.status == MessageStatus.SENT.value
        assert row.provider_message_id is not None
        assert row.provider_message_id.startswith("MOCK_")

    def test_send_increments_daily_counter(self, db_session):
        settings = _configure_tenant(db_session, TENANT_A, PHONE_A, daily_limit=5)
        service = WhatsAppService(db_session)

        service.send_whatsapp_message(tenant_id=TENANT_A, to_phone=PHONE_B, message="m1")
        service.send_whatsapp_message(tenant_id=TENANT_A, to_phone=PHONE_B, message="m2")

        db_session.refresh(settings)
        assert settings.whatsapp_sent_today == 2

    def test_send_rejects_when_daily_limit_reached(self, db_session):
        _configure_tenant(db_session, TENANT_A, PHONE_A, daily_limit=2)
        service = WhatsAppService(db_session)
        service.send_whatsapp_message(tenant_id=TENANT_A, to_phone=PHONE_B, message="m1")
        service.send_whatsapp_message(tenant_id=TENANT_A, to_phone=PHONE_B, message="m2")

        with pytest.raises(WhatsAppRateLimitExceeded):
            service.send_whatsapp_message(tenant_id=TENANT_A, to_phone=PHONE_B, message="m3")

    def test_send_resets_counter_at_new_utc_day(self, db_session):
        settings = _configure_tenant(db_session, TENANT_A, PHONE_A, daily_limit=10)
        # Pretend yesterday's counter is exhausted
        settings.whatsapp_sent_today = 10
        settings.limit_reset_date = datetime.utcnow() - timedelta(days=2)
        db_session.commit()

        service = WhatsAppService(db_session)
        outbound_id, success = service.send_whatsapp_message(
            tenant_id=TENANT_A, to_phone=PHONE_B, message="new day"
        )
        assert success is True

        db_session.refresh(settings)
        assert settings.whatsapp_sent_today == 1  # counter reset, then +1 for the send

    def test_zero_limit_means_unlimited(self, db_session):
        settings = _configure_tenant(db_session, TENANT_A, PHONE_A, daily_limit=0)
        # Set huge sent_today to prove 0 means unlimited rather than zero allowance.
        settings.whatsapp_sent_today = 99999
        db_session.commit()
        service = WhatsAppService(db_session)
        _, success = service.send_whatsapp_message(
            tenant_id=TENANT_A, to_phone=PHONE_B, message="unlimited send"
        )
        assert success is True


class TestHandleIncomingMessage:
    @pytest.fixture(autouse=True)
    def _force_mock_provider(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_PROVIDER", "mock")
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "test-internal-token")
        monkeypatch.setenv("CHAT_SERVICE_URL", "http://localhost:8000")
        yield

    def _record_inbound(self, db_session, tenant_id: str) -> str:
        _configure_tenant(db_session, tenant_id, PHONE_A)
        service = WhatsAppService(db_session)
        record, _ = service.record_inbound(
            tenant_id=tenant_id,
            provider_message_id="SM_inbound_e2e",
            from_phone=PHONE_B, to_phone=PHONE_A,
            message_body="What docs do I have?",
        )
        return record.id

    def test_full_round_trip_calls_chat_service_and_sends_reply(self, db_session):
        inbound_id = self._record_inbound(db_session, TENANT_A)

        # Mock the chat-service HTTP call
        fake_response = MagicMock()
        fake_response.json.return_value = {
            "content": "Here are your docs.",
            "sources": [],
            "session_id": "session-abc",
            "metadata": {},
        }
        fake_response.raise_for_status = MagicMock()

        with patch("app.services.whatsapp_service.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = False
            mock_client.post.return_value = fake_response
            mock_client_cls.return_value = mock_client

            service = WhatsAppService(db_session)
            outbound_id = service.handle_incoming_message(inbound_id)

        assert outbound_id is not None
        outbound = db_session.query(WhatsAppMessage).filter_by(id=outbound_id).first()
        assert outbound.direction == "outbound"
        assert outbound.message == "Here are your docs."
        assert outbound.tenant_id == TENANT_A

        # Inbound row is now annotated with the chat session
        inbound = db_session.query(WhatsAppMessage).filter_by(id=inbound_id).first()
        assert inbound.chat_session_id == "session-abc"

    def test_idempotent_when_already_processed(self, db_session):
        """If chat_session_id is already set, do not call chat-service again."""
        inbound_id = self._record_inbound(db_session, TENANT_A)
        # Mark as already processed
        inbound = db_session.query(WhatsAppMessage).filter_by(id=inbound_id).first()
        inbound.chat_session_id = "previously-replied"
        db_session.commit()

        with patch("app.services.whatsapp_service.httpx.Client") as mock_client_cls:
            service = WhatsAppService(db_session)
            outbound_id = service.handle_incoming_message(inbound_id)
            assert outbound_id is None
            mock_client_cls.assert_not_called()


class TestStatusCallbackWiring:
    """Verify the WHATSAPP_STATUS_CALLBACK_URL env var flows through to the
    provider's send_whatsapp() call so Twilio knows where to POST delivery
    status updates.
    """

    def test_explicit_callback_url_is_passed_to_provider(self, db_session, monkeypatch):
        monkeypatch.setenv("WHATSAPP_PROVIDER", "mock")
        monkeypatch.setenv(
            "WHATSAPP_STATUS_CALLBACK_URL",
            "https://api.chatcraft.cc/api/v1/whatsapp/webhooks/twilio/status",
        )
        _configure_tenant(db_session, TENANT_A, PHONE_A)
        service = WhatsAppService(db_session)

        captured = {}
        original = service._make_provider

        def capturing_make_provider(account_sid: str, auth_token: str):
            provider = original(account_sid, auth_token)
            real_send = provider.send_whatsapp

            def wrapper(*args, **kwargs):
                captured["status_callback"] = kwargs.get("status_callback")
                return real_send(*args, **kwargs)

            provider.send_whatsapp = wrapper  # type: ignore[method-assign]
            return provider

        service._make_provider = capturing_make_provider  # type: ignore[method-assign]

        service.send_whatsapp_message(tenant_id=TENANT_A, to_phone=PHONE_B, message="hi")

        assert captured["status_callback"] == (
            "https://api.chatcraft.cc/api/v1/whatsapp/webhooks/twilio/status"
        )

    def test_public_base_url_is_appended_with_standard_path(self, db_session, monkeypatch):
        monkeypatch.setenv("WHATSAPP_PROVIDER", "mock")
        monkeypatch.delenv("WHATSAPP_STATUS_CALLBACK_URL", raising=False)
        monkeypatch.setenv("PUBLIC_BASE_URL", "https://api.chatcraft.cc/")  # trailing slash on purpose
        service = WhatsAppService(db_session)

        url = service._status_callback_url()
        assert url == "https://api.chatcraft.cc/api/v1/whatsapp/webhooks/twilio/status"

    def test_neither_env_var_set_returns_none(self, db_session, monkeypatch):
        monkeypatch.setenv("WHATSAPP_PROVIDER", "mock")
        monkeypatch.delenv("WHATSAPP_STATUS_CALLBACK_URL", raising=False)
        monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
        service = WhatsAppService(db_session)

        assert service._status_callback_url() is None


class TestStripPrefix:
    def test_strips_whatsapp_prefix(self):
        assert _strip_whatsapp_prefix("whatsapp:+14155551234") == "+14155551234"

    def test_passes_through_unprefixed(self):
        assert _strip_whatsapp_prefix("+14155551234") == "+14155551234"

    def test_handles_empty(self):
        assert _strip_whatsapp_prefix("") == ""
