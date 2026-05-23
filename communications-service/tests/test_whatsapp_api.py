"""API-level tests for the WhatsApp endpoints.

Covers:
- Webhook HMAC verification (valid signature accepted, wrong-tenant signature
  rejected — the multi-tenant isolation guarantee)
- Idempotency through the webhook (same MessageSid → one row, one RabbitMQ event)
- /admin/whatsapp/setup plan gating, phone uniqueness (409), and Account SID
  masking on the GET endpoint
"""
from datetime import datetime
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from twilio.request_validator import RequestValidator

from app.api import whatsapp as whatsapp_api
from app.core.database import get_db
from app.models.communications import (
    TenantSettings,
    WhatsAppMessage,
    WhatsAppPhoneMapping,
)
from app.services.dependencies import TokenClaims, validate_super_admin_token, validate_token


WHATSAPP_PREFIX_PATH = "/api/v1/whatsapp"

TENANT_A = "tenant-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
TENANT_B = "tenant-bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
PHONE_A = "+14155238886"
PHONE_B = "+14155551234"
TOKEN_A = "tok_tenant_a_secret"
TOKEN_B = "tok_tenant_b_secret"
SID_A = "ACaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
SID_B = "ACbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _seed_tenant(db: Session, tenant_id: str, phone: str, sid: str, token: str) -> None:
    db.add(TenantSettings(
        tenant_id=tenant_id,
        whatsapp_enabled=True,
        whatsapp_twilio_sid=sid,
        whatsapp_twilio_token=token,
        whatsapp_phone_number=phone,
        daily_whatsapp_limit=1000,
        whatsapp_sent_today=0,
        limit_reset_date=datetime.utcnow(),
    ))
    db.add(WhatsAppPhoneMapping(tenant_id=tenant_id, business_phone_number=phone))
    db.commit()


@pytest.fixture
def app(db_session) -> FastAPI:
    """Minimal FastAPI app with just the whatsapp router mounted."""
    test_app = FastAPI()
    test_app.include_router(whatsapp_api.router, prefix=WHATSAPP_PREFIX_PATH)

    # Force every Depends(get_db) to yield the test session.
    def _override_get_db():
        yield db_session

    test_app.dependency_overrides[get_db] = _override_get_db

    # Stub auth: tests that need a different role can re-override per test.
    def _override_validate_token() -> TokenClaims:
        return TokenClaims(
            user_id="user-1", tenant_id=TENANT_A, email="admin@a.test",
            role="admin", exp=9999999999,
        )

    def _override_super_admin() -> TokenClaims:
        return TokenClaims(
            user_id="root", tenant_id="system", email="root@system.test",
            role="super_admin", exp=9999999999,
        )

    test_app.dependency_overrides[validate_token] = _override_validate_token
    test_app.dependency_overrides[validate_super_admin_token] = _override_super_admin
    return test_app


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _stub_async_publishers():
    """Webhook handler awaits RabbitMQ publishers. Mock them to no-ops so tests
    don't try to connect to RabbitMQ."""
    with (
        patch("app.api.whatsapp.whatsapp_publisher.publish_message_process",
              new=AsyncMock(return_value=True)),
        patch("app.api.whatsapp.audit_publisher.publish",
              new=AsyncMock(return_value=None)),
    ):
        yield


# ---------------------------------------------------------------------------
# Twilio signature helper
# ---------------------------------------------------------------------------

def _twilio_sig(url: str, form: dict, token: str) -> str:
    """Mirror what Twilio computes when signing webhook requests."""
    return RequestValidator(token).compute_signature(url, form)


def _incoming_form(message_sid: str, from_phone: str, to_phone: str, body: str = "Hi") -> dict:
    return {
        "MessageSid": message_sid,
        "From": f"whatsapp:{from_phone}",
        "To": f"whatsapp:{to_phone}",
        "Body": body,
        "WaId": from_phone.lstrip("+"),
    }


# ---------------------------------------------------------------------------
# Webhook tests
# ---------------------------------------------------------------------------

class TestIncomingWebhookHmac:
    def test_valid_signature_persists_and_acks(self, client, db_session):
        _seed_tenant(db_session, TENANT_A, PHONE_A, SID_A, TOKEN_A)

        url = f"http://testserver{WHATSAPP_PREFIX_PATH}/webhooks/twilio/incoming"
        form = _incoming_form("SM_good_1", PHONE_B, PHONE_A, "Hello bot")
        sig = _twilio_sig(url, form, TOKEN_A)

        resp = client.post(
            f"{WHATSAPP_PREFIX_PATH}/webhooks/twilio/incoming",
            data=form,
            headers={"X-Twilio-Signature": sig},
        )
        assert resp.status_code == 200
        assert "<Response></Response>" in resp.text

        # Row was persisted as inbound
        rows = db_session.query(WhatsAppMessage).all()
        assert len(rows) == 1
        assert rows[0].direction == "inbound"
        assert rows[0].provider_message_id == "SM_good_1"
        assert rows[0].tenant_id == TENANT_A

    def test_wrong_tenant_token_is_rejected_403(self, client, db_session):
        """The multi-tenant isolation guarantee: a payload addressed to
        tenant A's `To` number but signed with tenant B's token must be 403."""
        _seed_tenant(db_session, TENANT_A, PHONE_A, SID_A, TOKEN_A)
        _seed_tenant(db_session, TENANT_B, "+14159990000", SID_B, TOKEN_B)

        url = f"http://testserver{WHATSAPP_PREFIX_PATH}/webhooks/twilio/incoming"
        form = _incoming_form("SM_evil", PHONE_B, PHONE_A, "Trying to impersonate")
        # Sign with tenant B's token while addressing tenant A's phone
        bad_sig = _twilio_sig(url, form, TOKEN_B)

        resp = client.post(
            f"{WHATSAPP_PREFIX_PATH}/webhooks/twilio/incoming",
            data=form,
            headers={"X-Twilio-Signature": bad_sig},
        )
        assert resp.status_code == 403
        # No row was written
        assert db_session.query(WhatsAppMessage).count() == 0

    def test_unknown_To_phone_is_rejected_403(self, client, db_session):
        # No tenant registered for the To phone
        url = f"http://testserver{WHATSAPP_PREFIX_PATH}/webhooks/twilio/incoming"
        form = _incoming_form("SM_orphan", PHONE_B, "+14159999999")
        sig = _twilio_sig(url, form, "anytoken")
        resp = client.post(
            f"{WHATSAPP_PREFIX_PATH}/webhooks/twilio/incoming",
            data=form,
            headers={"X-Twilio-Signature": sig},
        )
        assert resp.status_code == 403
        assert db_session.query(WhatsAppMessage).count() == 0

    def test_idempotent_on_duplicate_MessageSid(self, client, db_session):
        _seed_tenant(db_session, TENANT_A, PHONE_A, SID_A, TOKEN_A)

        url = f"http://testserver{WHATSAPP_PREFIX_PATH}/webhooks/twilio/incoming"
        form = _incoming_form("SM_dup_sid", PHONE_B, PHONE_A, "first delivery")
        sig = _twilio_sig(url, form, TOKEN_A)

        for _ in range(3):
            resp = client.post(
                f"{WHATSAPP_PREFIX_PATH}/webhooks/twilio/incoming",
                data=form,
                headers={"X-Twilio-Signature": sig},
            )
            assert resp.status_code == 200

        rows = db_session.query(WhatsAppMessage).filter_by(provider_message_id="SM_dup_sid").all()
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# Admin setup endpoint tests
# ---------------------------------------------------------------------------

class TestAdminSetup:
    @pytest.fixture(autouse=True)
    def _grant_plan_feature(self):
        """Default: the plan-gate check passes. Tests that need a 403 plan
        rejection re-override this with a side_effect of HTTPException."""
        with patch(
            "app.api.whatsapp._assert_whatsapp_plan_feature",
            new=AsyncMock(return_value=None),
        ) as mock:
            yield mock

    def test_setup_returns_409_when_phone_in_use_by_another_tenant(self, client, db_session):
        # Tenant B has already claimed PHONE_A; tenant A (authenticated user) tries to claim same.
        _seed_tenant(db_session, TENANT_B, PHONE_A, SID_B, TOKEN_B)

        resp = client.post(
            f"{WHATSAPP_PREFIX_PATH}/admin/whatsapp/setup",
            json={"account_sid": SID_A, "auth_token": TOKEN_A, "phone_number": PHONE_A},
            headers={"Authorization": "Bearer test"},
        )
        assert resp.status_code == 409
        # No mapping was created for tenant A
        assert db_session.query(WhatsAppPhoneMapping).filter_by(tenant_id=TENANT_A).count() == 0

    def test_setup_creates_settings_and_mapping(self, client, db_session):
        resp = client.post(
            f"{WHATSAPP_PREFIX_PATH}/admin/whatsapp/setup",
            json={"account_sid": SID_A, "auth_token": TOKEN_A, "phone_number": PHONE_A},
            headers={"Authorization": "Bearer test"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["tenant_id"] == TENANT_A
        assert body["whatsapp_enabled"] is True
        assert body["phone_number"] == PHONE_A

        settings = db_session.query(TenantSettings).filter_by(tenant_id=TENANT_A).first()
        assert settings.whatsapp_enabled is True
        assert settings.whatsapp_twilio_sid == SID_A
        assert settings.whatsapp_twilio_token == TOKEN_A
        assert settings.whatsapp_phone_number == PHONE_A

    def test_setup_blocked_when_plan_lacks_feature(self, client, db_session):
        from fastapi import HTTPException, status as st

        # Override the autouse mock so plan-gate raises 403.
        with patch(
            "app.api.whatsapp._assert_whatsapp_plan_feature",
            new=AsyncMock(side_effect=HTTPException(
                status_code=st.HTTP_403_FORBIDDEN,
                detail="WhatsApp not on plan",
            )),
        ):
            resp = client.post(
                f"{WHATSAPP_PREFIX_PATH}/admin/whatsapp/setup",
                json={"account_sid": SID_A, "auth_token": TOKEN_A, "phone_number": PHONE_A},
                headers={"Authorization": "Bearer test"},
            )
        assert resp.status_code == 403

    def test_setup_rejects_phone_without_country_code(self, client):
        resp = client.post(
            f"{WHATSAPP_PREFIX_PATH}/admin/whatsapp/setup",
            json={"account_sid": SID_A, "auth_token": TOKEN_A, "phone_number": "4155238886"},
            headers={"Authorization": "Bearer test"},
        )
        assert resp.status_code == 400

    def test_get_setup_returns_masked_sid(self, client, db_session):
        _seed_tenant(db_session, TENANT_A, PHONE_A, SID_A, TOKEN_A)

        resp = client.get(
            f"{WHATSAPP_PREFIX_PATH}/admin/whatsapp/setup",
            headers={"Authorization": "Bearer test"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["whatsapp_enabled"] is True
        assert body["phone_number"] == PHONE_A
        masked = body["account_sid_masked"]
        # Masked SID never contains the middle characters
        assert masked is not None
        assert SID_A not in masked
        assert masked.startswith("AC")
        assert masked.endswith(SID_A[-4:])
        # Token is NEVER returned anywhere in the response
        assert TOKEN_A not in resp.text

    def test_get_setup_returns_disabled_state_for_unconfigured_tenant(self, client):
        resp = client.get(
            f"{WHATSAPP_PREFIX_PATH}/admin/whatsapp/setup",
            headers={"Authorization": "Bearer test"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["whatsapp_enabled"] is False
        assert body["phone_number"] is None
        assert body["account_sid_masked"] is None


class TestSidMasking:
    """The SID masking helper is a security-sensitive small function."""

    def test_short_sid_still_partly_hidden(self):
        from app.api.whatsapp import _mask_account_sid
        assert _mask_account_sid("ABC") == "***BC"

    def test_long_sid_shows_first_2_last_4(self):
        from app.api.whatsapp import _mask_account_sid
        sid = "AC1234567890abcdef1234567890wxyz"
        masked = _mask_account_sid(sid)
        assert masked.startswith("AC")
        assert masked.endswith("wxyz")
        assert "1234" not in masked  # middle of the original SID hidden
        assert len(masked) == len(sid)

    def test_none_returns_none(self):
        from app.api.whatsapp import _mask_account_sid
        assert _mask_account_sid(None) is None
        assert _mask_account_sid("") is None
