"""WhatsApp HTTP API.

Endpoints:
- POST /admin/whatsapp/setup    — tenant admin registers/updates their own
                                  Twilio WhatsApp Business credentials + number.
- DELETE /admin/whatsapp/setup  — tenant admin disables WhatsApp.
- GET  /messages                — list messages for the authenticated tenant.
- GET  /messages/{id}           — single message.
- GET  /admin/messages/{tenant_id} — super-admin variant.
- POST /webhooks/twilio/incoming — Twilio webhook (filled in by Phase 5).
- POST /webhooks/twilio/status   — Twilio webhook (filled in by Phase 5).

Setup endpoints are gated on `Plan.has_whatsapp` (a 'Pro+' feature),
verified by forwarding the caller's bearer token to billing-service's
`/api/v1/subscriptions/features` endpoint.
"""
import os
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.logging_config import get_logger
from ..models.communications import (
    TenantSettings,
    WhatsAppMessage,
    WhatsAppPhoneMapping,
)
from ..services.audit_publisher import audit_publisher
from ..services.dependencies import TokenClaims, validate_super_admin_token, validate_token
from ..services.whatsapp_publisher import whatsapp_publisher
from ..services.whatsapp_service import WhatsAppService, _strip_whatsapp_prefix


router = APIRouter()
security = HTTPBearer(auto_error=False)
webhook_logger = get_logger("whatsapp_webhook")


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class WhatsAppSetupRequest(BaseModel):
    account_sid: str = Field(..., min_length=1, description="Twilio Account SID")
    auth_token: str = Field(..., min_length=1, description="Twilio Auth Token")
    phone_number: str = Field(..., min_length=4, description="Tenant's approved WhatsApp Business number, E.164 (e.g. +14155238886)")


class WhatsAppSetupResponse(BaseModel):
    tenant_id: str
    whatsapp_enabled: bool
    phone_number: str


class WhatsAppConfigResponse(BaseModel):
    """Current WhatsApp configuration readout for a tenant.

    Returns whatsapp_enabled status plus the configured phone number and a
    last-4 mask of the Twilio Account SID. The auth token is NEVER returned.
    """
    tenant_id: str
    whatsapp_enabled: bool
    phone_number: Optional[str] = None
    account_sid_masked: Optional[str] = None


def _mask_account_sid(sid: Optional[str]) -> Optional[str]:
    """Twilio Account SIDs start with 'AC' + 32 hex chars. Show first 2 + last 4 only."""
    if not sid:
        return None
    if len(sid) <= 6:
        return "***" + sid[-2:]
    return sid[:2] + ("*" * (len(sid) - 6)) + sid[-4:]


class WhatsAppMessageResponse(BaseModel):
    id: str
    tenant_id: str
    direction: str
    wa_id: Optional[str]
    to_phone: str
    from_phone: str
    message: str
    status: str
    provider_message_id: Optional[str]
    sent_at: Optional[str]
    delivered_at: Optional[str]
    error_message: Optional[str]
    created_at: Optional[str]


class WhatsAppListResponse(BaseModel):
    messages: List[WhatsAppMessageResponse]
    total: int
    page: int
    size: int


def _to_response(record: WhatsAppMessage) -> WhatsAppMessageResponse:
    return WhatsAppMessageResponse(
        id=record.id,
        tenant_id=record.tenant_id,
        direction=record.direction,
        wa_id=record.wa_id,
        to_phone=record.to_phone,
        from_phone=record.from_phone,
        message=record.message,
        status=record.status,
        provider_message_id=record.provider_message_id,
        sent_at=record.sent_at.isoformat() if record.sent_at else None,
        delivered_at=record.delivered_at.isoformat() if record.delivered_at else None,
        error_message=record.error_message,
        created_at=record.created_at.isoformat() if record.created_at else None,
    )


# ---------------------------------------------------------------------------
# Plan gating helper
# ---------------------------------------------------------------------------


async def _assert_whatsapp_plan_feature(bearer_token: str) -> None:
    """Forward the caller's bearer token to billing-service and confirm the
    tenant's plan has the `whatsapp` feature flag enabled.

    Raises 403 if not entitled; 502 if billing-service is unreachable.
    """
    # Default matches the gateway-config dev port for billing-service.
    # Override via BILLING_SERVICE_URL env var in .env.
    billing_url = os.environ.get("BILLING_SERVICE_URL", "http://localhost:8004")
    url = f"{billing_url.rstrip('/')}/api/v1/subscriptions/features"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {bearer_token}"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not reach billing-service for plan check: {exc}",
        )
    if response.status_code == status.HTTP_401_UNAUTHORIZED:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token rejected by billing-service")
    if response.status_code != status.HTTP_200_OK:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Billing-service returned {response.status_code}",
        )

    try:
        features = (response.json() or {}).get("features") or {}
    except ValueError:
        features = {}

    if not features.get("whatsapp"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="WhatsApp is not available on your current plan. Upgrade to enable.",
        )


# ---------------------------------------------------------------------------
# Admin: setup / disable
# ---------------------------------------------------------------------------


@router.get("/admin/whatsapp/setup", response_model=WhatsAppConfigResponse)
async def get_whatsapp_setup(
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db),
):
    """Return the authenticated tenant's current WhatsApp configuration.

    Always returns 200 — `whatsapp_enabled=false` and `null` fields indicate
    the tenant has not configured WhatsApp yet. The auth token is never
    returned; the Account SID is returned in masked form.
    """
    if claims.role != "admin" and claims.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant admin privileges required",
        )
    settings = (
        db.query(TenantSettings)
        .filter(TenantSettings.tenant_id == claims.tenant_id)
        .first()
    )
    return WhatsAppConfigResponse(
        tenant_id=claims.tenant_id,
        whatsapp_enabled=bool(settings and settings.whatsapp_enabled),
        phone_number=settings.whatsapp_phone_number if settings else None,
        account_sid_masked=_mask_account_sid(settings.whatsapp_twilio_sid) if settings else None,
    )


@router.get("/admin/config/{tenant_id}", response_model=WhatsAppConfigResponse)
async def get_whatsapp_setup_for_tenant(
    tenant_id: str,
    claims: TokenClaims = Depends(validate_super_admin_token),
    db: Session = Depends(get_db),
):
    """Super-admin variant: read any tenant's WhatsApp configuration.

    Used by the super-admin tenant-detail Communications tab. Auth token is
    never returned; Account SID is masked.
    """
    settings = (
        db.query(TenantSettings).filter(TenantSettings.tenant_id == tenant_id).first()
    )
    return WhatsAppConfigResponse(
        tenant_id=tenant_id,
        whatsapp_enabled=bool(settings and settings.whatsapp_enabled),
        phone_number=settings.whatsapp_phone_number if settings else None,
        account_sid_masked=_mask_account_sid(settings.whatsapp_twilio_sid) if settings else None,
    )


@router.post("/admin/whatsapp/setup", response_model=WhatsAppSetupResponse)
async def setup_whatsapp(
    request: WhatsAppSetupRequest,
    claims: TokenClaims = Depends(validate_token),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
):
    """Register or update the tenant's Twilio WhatsApp Business credentials.

    Each tenant must supply their own SID + Auth Token + approved business
    phone number. The phone number is also written to WhatsAppPhoneMapping for
    inbound webhook routing — globally unique across tenants.
    """
    if claims.role != "admin" and claims.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant admin privileges required",
        )
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required")

    await _assert_whatsapp_plan_feature(credentials.credentials)

    normalised_phone = _strip_whatsapp_prefix(request.phone_number).strip()
    if not normalised_phone.startswith("+"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="phone_number must include the country code (e.g. +14155238886)",
        )

    # Get-or-create TenantSettings
    settings = (
        db.query(TenantSettings).filter(TenantSettings.tenant_id == claims.tenant_id).first()
    )
    if not settings:
        settings = TenantSettings(tenant_id=claims.tenant_id)
        db.add(settings)
        db.flush()

    # Upsert phone mapping; UNIQUE on business_phone_number prevents another
    # tenant from claiming a number that's already in use.
    existing_mapping = (
        db.query(WhatsAppPhoneMapping)
        .filter(WhatsAppPhoneMapping.tenant_id == claims.tenant_id)
        .first()
    )
    if existing_mapping:
        # If the tenant is changing their number, update in place
        existing_mapping.business_phone_number = normalised_phone
    else:
        existing_mapping = WhatsAppPhoneMapping(
            tenant_id=claims.tenant_id,
            business_phone_number=normalised_phone,
        )
        db.add(existing_mapping)

    settings.whatsapp_enabled = True
    settings.whatsapp_twilio_sid = request.account_sid
    settings.whatsapp_twilio_token = request.auth_token
    settings.whatsapp_phone_number = normalised_phone

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Phone number {normalised_phone} is already registered to another tenant",
        )

    try:
        await audit_publisher.publish(
            action_type="whatsapp.configured",
            tier="config",
            source_service="communications-service",
            tenant_id=claims.tenant_id,
            actor_user_id=claims.user_id,
            actor_email=claims.email,
            resource_type="tenant_settings",
            resource_id=claims.tenant_id,
            after_state={"whatsapp_enabled": True, "phone_number": normalised_phone},
        )
    except Exception:
        pass

    return WhatsAppSetupResponse(
        tenant_id=claims.tenant_id,
        whatsapp_enabled=True,
        phone_number=normalised_phone,
    )


@router.delete("/admin/whatsapp/setup")
async def disable_whatsapp(
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db),
):
    """Disable WhatsApp for the tenant and remove the phone mapping.

    Does NOT require a plan-feature check — a tenant whose plan has been
    downgraded must still be able to clean up.
    """
    if claims.role != "admin" and claims.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant admin privileges required",
        )

    settings = (
        db.query(TenantSettings).filter(TenantSettings.tenant_id == claims.tenant_id).first()
    )
    if settings:
        settings.whatsapp_enabled = False
        settings.whatsapp_twilio_sid = None
        settings.whatsapp_twilio_token = None
        settings.whatsapp_phone_number = None

    db.query(WhatsAppPhoneMapping).filter(
        WhatsAppPhoneMapping.tenant_id == claims.tenant_id
    ).delete()

    db.commit()

    try:
        await audit_publisher.publish(
            action_type="whatsapp.disabled",
            tier="config",
            source_service="communications-service",
            tenant_id=claims.tenant_id,
            actor_user_id=claims.user_id,
            actor_email=claims.email,
            resource_type="tenant_settings",
            resource_id=claims.tenant_id,
            after_state={"whatsapp_enabled": False},
        )
    except Exception:
        pass

    return {"tenant_id": claims.tenant_id, "whatsapp_enabled": False}


# ---------------------------------------------------------------------------
# Messages list / detail
# ---------------------------------------------------------------------------


@router.get("/messages", response_model=WhatsAppListResponse)
async def list_messages(
    page: int = 1,
    size: int = 50,
    status_filter: Optional[str] = None,
    direction: Optional[str] = None,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db),
):
    if page < 1:
        page = 1
    if size < 1 or size > 200:
        size = min(max(size, 1), 200)

    skip = (page - 1) * size
    service = WhatsAppService(db)
    messages = service.list_tenant_messages(
        tenant_id=claims.tenant_id,
        skip=skip,
        limit=size,
        status=status_filter,
        direction=direction,
    )

    query = db.query(WhatsAppMessage).filter(WhatsAppMessage.tenant_id == claims.tenant_id)
    if status_filter:
        query = query.filter(WhatsAppMessage.status == status_filter)
    if direction:
        query = query.filter(WhatsAppMessage.direction == direction)
    total = query.count()

    return WhatsAppListResponse(
        messages=[_to_response(m) for m in messages],
        total=total,
        page=page,
        size=size,
    )


@router.get("/messages/{message_id}", response_model=WhatsAppMessageResponse)
async def get_message(
    message_id: str,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db),
):
    service = WhatsAppService(db)
    record = service.get_message(message_id, claims.tenant_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WhatsApp message not found")
    return _to_response(record)


# ---------------------------------------------------------------------------
# Twilio webhooks — two-step HMAC verification
# ---------------------------------------------------------------------------


def _verify_twilio_signature(url: str, form: Dict[str, str], signature: str, auth_token: str) -> bool:
    """Validate Twilio's X-Twilio-Signature HMAC-SHA1.

    Twilio computes the signature over `url + concat(sorted(k+v))`.
    """
    try:
        from twilio.request_validator import RequestValidator
    except ImportError:
        webhook_logger.error("twilio package missing — cannot verify webhooks")
        return False
    return RequestValidator(auth_token).validate(url, form, signature)


def _public_webhook_url(request: Request) -> str:
    """Build the URL Twilio used when signing the request.

    Twilio signs against the URL Twilio itself was configured to POST to —
    i.e. the public-facing URL (e.g. `https://api.chatcraft.cc/...`). The
    request arriving at this FastAPI app, however, has typically been
    proxied through a load-balancer and a gateway, so `request.url` and
    even the `Host` header have been rewritten to internal hostnames
    (e.g. `communications-service:8000`).

    Resolution order (highest priority wins):
      1. `PUBLIC_BASE_URL` env var — explicit, robust against any proxy
         chain. Recommended in any non-local deployment.
      2. `X-Forwarded-Proto` + `X-Forwarded-Host` headers — when the
         gateway forwards them faithfully.
      3. Raw request URL — the local dev case where there's no proxy.
    """
    public_base = os.environ.get("PUBLIC_BASE_URL")
    if public_base:
        return f"{public_base.rstrip('/')}{request.url.path}"

    scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = (
        request.headers.get("x-forwarded-host")
        or request.headers.get("host")
        or request.url.netloc
    )
    return f"{scheme}://{host}{request.url.path}"


@router.post("/webhooks/twilio/incoming")
async def twilio_incoming_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """Receive an inbound WhatsApp message from Twilio.

    Flow:
      1. Parse form payload (do NOT trust yet)
      2. Resolve tenant from `To` phone via WhatsAppPhoneMapping
      3. Load that tenant's Twilio auth_token from TenantSettings
      4. Verify HMAC against that token — reject 403 on mismatch
      5. Persist inbound row (idempotent via UNIQUE on provider_message_id)
      6. Publish whatsapp.message.process to RabbitMQ
      7. Return TwiML empty response within <1s
    """
    form = await request.form()
    form_dict: Dict[str, str] = {k: str(v) for k, v in form.items()}

    provider_message_id = form_dict.get("MessageSid")
    from_phone = form_dict.get("From", "")
    to_phone = form_dict.get("To", "")
    body = form_dict.get("Body", "")
    wa_id = form_dict.get("WaId") or _strip_whatsapp_prefix(from_phone)
    signature = request.headers.get("X-Twilio-Signature", "")

    if not provider_message_id or not from_phone or not to_phone:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed Twilio payload")

    service = WhatsAppService(db)
    tenant_id = service.resolve_tenant_from_phone(to_phone)
    if not tenant_id:
        # Unknown To-number — reject without leaking which numbers are registered.
        # Log both the raw value and the normalized lookup key — a leading
        # space typically means the client sent '+' literally in a
        # form-urlencoded body where '+' decodes to space; use
        # --data-urlencode or %2B in tests.
        webhook_logger.warning(
            "Inbound for unknown business number",
            extra={
                "raw_to": to_phone,
                "lookup_key": _strip_whatsapp_prefix(to_phone),
            },
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unknown destination")

    auth_token = service.get_tenant_auth_token(tenant_id)
    if not auth_token:
        webhook_logger.error(f"Tenant {tenant_id} has no auth_token configured")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant misconfigured")

    url = _public_webhook_url(request)
    if not _verify_twilio_signature(url, form_dict, signature, auth_token):
        webhook_logger.warning(
            "Twilio HMAC verification failed",
            extra={"tenant_id": tenant_id, "url": url, "message_sid": provider_message_id},
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Twilio signature")

    record, is_new = service.record_inbound(
        tenant_id=tenant_id,
        provider_message_id=provider_message_id,
        from_phone=from_phone,
        to_phone=to_phone,
        message_body=body,
        wa_id=wa_id,
    )

    # ACK Twilio with an empty TwiML — the consumer will send the actual reply
    # via an outbound API call.
    if is_new and record:
        try:
            await audit_publisher.publish(
                action_type="whatsapp.message.received",
                tier="data",
                source_service="communications-service",
                tenant_id=tenant_id,
                actor_type="system",
                resource_type="whatsapp_message",
                resource_id=record.id,
                event_metadata={
                    "wa_id": record.wa_id,
                    "provider_message_id": provider_message_id,
                    "from_phone": record.from_phone,
                    "to_phone": record.to_phone,
                    "message_length": len(record.message or ""),
                },
            )
        except Exception:
            pass

        published = await whatsapp_publisher.publish_message_process(
            tenant_id=tenant_id,
            inbound_message_id=record.id,
            provider_message_id=provider_message_id,
            wa_id=record.wa_id,
        )
        if not published:
            webhook_logger.error(
                "Inbound persisted but publish failed — message will not be answered",
                extra={"inbound_message_id": record.id, "tenant_id": tenant_id},
            )

    return Response(
        content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        media_type="application/xml",
    )


@router.post("/webhooks/twilio/status")
async def twilio_status_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """Receive a Twilio delivery-status callback for an outbound message.

    Same two-step HMAC verification as the inbound webhook: the outbound row
    tells us which tenant sent the message, so we look up their auth_token to
    verify the signature.
    """
    form = await request.form()
    form_dict: Dict[str, str] = {k: str(v) for k, v in form.items()}

    provider_message_id = form_dict.get("MessageSid")
    signature = request.headers.get("X-Twilio-Signature", "")
    if not provider_message_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing MessageSid")

    # The outbound WhatsAppMessage row holds tenant_id; use it to load auth_token.
    record = (
        db.query(WhatsAppMessage)
        .filter(WhatsAppMessage.provider_message_id == provider_message_id)
        .first()
    )
    if not record:
        # Twilio retries status callbacks; an unknown SID could be a race or a forged call.
        webhook_logger.info(f"Status callback for unknown MessageSid {provider_message_id}")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    service = WhatsAppService(db)
    auth_token = service.get_tenant_auth_token(record.tenant_id)
    if not auth_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant misconfigured")

    url = _public_webhook_url(request)
    if not _verify_twilio_signature(url, form_dict, signature, auth_token):
        webhook_logger.warning(
            "Twilio HMAC verification failed (status callback)",
            extra={"tenant_id": record.tenant_id, "url": url, "message_sid": provider_message_id},
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Twilio signature")

    service.handle_delivery_status(form_dict)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/admin/messages/{tenant_id}", response_model=WhatsAppListResponse)
async def list_messages_for_tenant_admin(
    tenant_id: str,
    page: int = 1,
    size: int = 50,
    status_filter: Optional[str] = None,
    direction: Optional[str] = None,
    claims: TokenClaims = Depends(validate_super_admin_token),
    db: Session = Depends(get_db),
):
    if page < 1:
        page = 1
    if size < 1 or size > 200:
        size = min(max(size, 1), 200)

    skip = (page - 1) * size
    service = WhatsAppService(db)
    messages = service.list_tenant_messages(
        tenant_id=tenant_id,
        skip=skip,
        limit=size,
        status=status_filter,
        direction=direction,
    )

    query = db.query(WhatsAppMessage).filter(WhatsAppMessage.tenant_id == tenant_id)
    if status_filter:
        query = query.filter(WhatsAppMessage.status == status_filter)
    if direction:
        query = query.filter(WhatsAppMessage.direction == direction)
    total = query.count()

    return WhatsAppListResponse(
        messages=[_to_response(m) for m in messages],
        total=total,
        page=page,
        size=size,
    )
