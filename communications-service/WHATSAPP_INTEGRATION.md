# WhatsApp Integration

This service owns the WhatsApp Business channel for ChatCraft tenants. End-users
text the tenant's approved WhatsApp Business number; the message is routed
through Twilio → this service → chat-service (RAG pipeline) → reply sent back
through Twilio.

> History note: an earlier version of this document existed as a TODO list with
> all phases marked `✅` aspirationally. None of that code was ever shipped.
> This document was rewritten on 2026-05-22 to reflect the actual implementation
> landed under the WhatsApp integration commits. Refer to
> `/Users/adebola/.claude/plans/what-is-the-best-wiggly-spark.md` for the
> original design rationale.

---

## Scope (v1)

**Per-tenant own numbers only.** No shared sandbox flow. Each tenant must:
1. Open their own Twilio account.
2. Complete Twilio's WhatsApp Business onboarding to get an approved sender
   number (the Facebook Business Verification step is the slow one).
3. POST `/api/v1/whatsapp/admin/whatsapp/setup` with their Account SID, Auth
   Token, and approved phone number.

Plan-gated on `Plan.has_whatsapp` (Pro+). Free / Basic plans get HTTP 403 from
the setup endpoint.

---

## Architecture

```
WhatsApp end-user
       │
       ▼
Twilio (tenant's own account)  signs webhook with X-Twilio-Signature HMAC-SHA1
       │                       (using THAT tenant's auth_token)
       ▼  POST /api/v1/whatsapp/webhooks/twilio/incoming   [public]
communications-service  ── parse form (do NOT trust yet)
                        ── resolve tenant from `To` phone via WhatsAppPhoneMapping
                        ── load tenant's auth_token from TenantSettings
                        ── verify HMAC  → 403 on mismatch
                        ── persist inbound row (UNIQUE on provider_message_id)
                        ── ACK Twilio with empty TwiML <1s
                        ── publish to RabbitMQ: whatsapp.message.process
       │
       ▼
WhatsAppConsumer  (aio_pika, queue `whatsapp.process`)
       │
       ▼
WhatsAppService.handle_incoming_message
       │   skip if inbound.chat_session_id already set (idempotent)
       ▼  POST internal: chat-service /api/v1/internal/chat/generate
chat-service  ── X-Internal-Service-Token header
              ── resolve-or-create ChatSession by (tenant_id, user_identifier=wa_id)
              ── ChatService.generate_response(tenant_id, message, session_id)
              ── persist user + assistant ChatMessage rows
              ── return {content, sources, session_id, metadata}
       │
       ▼
WhatsAppService → TwilioWhatsAppProvider(tenant_sid, tenant_token).send
       │
       ▼  POST /api/v1/whatsapp/webhooks/twilio/status   [public]
communications-service verifies HMAC, updates outbound row delivery status
```

The async hop between webhook and AI exists because Twilio retries any webhook
not ACK'd in ~15s, while AI generation can take 5–30s. Inline processing
would risk duplicate replies.

---

## HTTP API

All paths are mounted at `${API_V1_STR}/whatsapp`.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/admin/whatsapp/setup` | Bearer (tenant admin) + plan-gate | Register Twilio creds + phone number |
| DELETE | `/admin/whatsapp/setup` | Bearer (tenant admin) | Disable WhatsApp for the tenant |
| GET | `/messages` | Bearer | List messages for the authenticated tenant |
| GET | `/messages/{message_id}` | Bearer | Get a single message |
| GET | `/admin/messages/{tenant_id}` | Bearer (super admin) | List messages for any tenant |
| POST | `/webhooks/twilio/incoming` | None (HMAC-verified per-tenant) | Inbound from Twilio |
| POST | `/webhooks/twilio/status` | None (HMAC-verified per-tenant) | Delivery status from Twilio |

### `POST /admin/whatsapp/setup`

```json
{
  "account_sid": "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "auth_token":  "your_twilio_auth_token",
  "phone_number": "+14155238886"
}
```

Returns 200 with `{tenant_id, whatsapp_enabled, phone_number}`. The phone
number must be globally unique across tenants — a `409 Conflict` is returned
if another tenant has already claimed it.

---

## Data model

Three changes under `app/models/communications.py` (migration
`alembic/versions/20260522_add_whatsapp_support.py`):

1. **`whatsapp_messages`** — inbound + outbound rows.
   `UNIQUE(provider_message_id)` provides webhook idempotency.
2. **`whatsapp_phone_mappings`** — `tenant_id ↔ business_phone_number`,
   `UNIQUE(business_phone_number)`. The lookup-by-`To`-phone target.
3. **`tenant_settings`** gains four columns:
   `whatsapp_enabled`, `whatsapp_twilio_sid`, `whatsapp_twilio_token`,
   `whatsapp_phone_number`.

The `Plan` model in billing-service gains `has_whatsapp` (migration
`billing-service/alembic/versions/20260522_add_has_whatsapp_to_plans.py`).
It is exposed in the `features` dict returned by `GET /api/v1/plans/...` and
`GET /api/v1/subscriptions/features`.

**Credential storage**: Twilio Account SID and Auth Token are stored as plain
text on `tenant_settings` for consistency with how other tenant-supplied
secrets are kept across the codebase. This is a known compromise — revisit
when a project-wide secrets-encryption standard lands.

---

## Code layout

```
communications-service/app/
├── api/
│   └── whatsapp.py                 # HTTP router (admin + webhooks + list)
├── services/
│   ├── whatsapp_provider.py        # ABC + TwilioWhatsAppProvider + MockWhatsAppProvider
│   ├── whatsapp_service.py         # orchestration: record, send, handle_incoming, handle_delivery_status
│   ├── whatsapp_publisher.py       # aio_pika producer for whatsapp.events
│   └── whatsapp_consumer.py        # aio_pika consumer for whatsapp.process
├── models/communications.py        # +WhatsAppMessage, +WhatsAppPhoneMapping, +tenant_settings columns
└── alembic/versions/20260522_add_whatsapp_support.py

chat-service/app/
├── api/chat_api.py                 # POST /api/v1/internal/chat/generate
└── services/dependencies.py        # +validate_internal_service

billing-service/app/
├── models/plan.py                  # +has_whatsapp
├── api/plans.py                    # +whatsapp in features dict
└── alembic/versions/20260522_add_has_whatsapp_to_plans.py
```

---

## Environment variables

### `communications-service/.env`

| Variable | Required | Default | Notes |
|---|---|---|---|
| `WHATSAPP_PROVIDER` | yes | `mock` | Set to `twilio` in any environment that talks to real Twilio. `mock` short-circuits the provider without touching the network. |
| `CHAT_SERVICE_URL` | yes | `http://localhost:8000` | Base URL of chat-service for the internal generate call. |
| `INTERNAL_SERVICE_TOKEN` | yes | — | Shared static secret. **Must match `chat-service/.env`**. |
| `BILLING_SERVICE_URL` | yes | `http://localhost:8004` | Used by `/admin/whatsapp/setup` to verify the tenant's plan has the `whatsapp` feature. Must match where billing-service is actually listening. |
| `WHATSAPP_STATUS_CALLBACK_URL` | no | — | Full URL Twilio will POST delivery-status updates to for outbound messages. E.g. `https://api.chatcraft.cc/api/v1/whatsapp/webhooks/twilio/status`. If unset, falls back to `${PUBLIC_BASE_URL}/api/v1/whatsapp/webhooks/twilio/status`. If neither env var is set, no `status_callback` is sent to Twilio and only whatever default the tenant has configured on the number in the Twilio Console will fire. |
| `PUBLIC_BASE_URL` | **yes in any non-local deployment** | — | Public base URL of the gateway (e.g. `https://api.chatcraft.cc`). Used for **two** things: (1) reconstructing the URL Twilio signed when verifying incoming webhooks — without this, multi-proxy deployments will rebuild the URL using the internal service name and HMAC verification will fail with 403; (2) deriving the status-callback URL when `WHATSAPP_STATUS_CALLBACK_URL` is not explicitly set. |

Twilio credentials are **not** stored in `.env` — they live in the database
per tenant. The existing `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` env vars
remain used by the SMS service (single Twilio account) and do not affect
WhatsApp.

### `chat-service/.env`

| Variable | Required | Default | Notes |
|---|---|---|---|
| `INTERNAL_SERVICE_TOKEN` | yes | — | Shared static secret. Must match `communications-service/.env`. |

---

## Local development

```bash
# 1. Apply migrations
cd communications-service && alembic upgrade head
cd ../billing-service && alembic upgrade head

# 2. Run services
cd ../communications-service && uvicorn app.main:app --port 8003 --reload &
cd ../chat-service          && uvicorn app.main:app --port 8000 --reload &

# 3. Configure a test tenant (any tenant_admin can do this)
curl -X POST http://localhost:8003/api/v1/whatsapp/admin/whatsapp/setup \
  -H "Authorization: Bearer <tenant-admin-jwt>" \
  -H "Content-Type: application/json" \
  -d '{"account_sid": "ACtest", "auth_token": "tok_fake_12345", "phone_number": "+14155238886"}'

# 4. Simulate an inbound webhook (mock provider — signature must be computed against the token above)
curl -X POST http://localhost:8003/api/v1/whatsapp/webhooks/twilio/incoming \
  -H "X-Twilio-Signature: <hmac-sha1-base64-using-tok_fake_12345>" \
  -d "From=whatsapp:+14155551234&To=whatsapp:+14155238886&Body=Hello&MessageSid=SMtest1"

# Expected: 200 ACK in <1s; the consumer picks up the queued event;
# the MockWhatsAppProvider prints the AI reply to stdout.
```

---

## Real-tenant Twilio e2e (no sandbox path)

1. Acquire a Twilio WhatsApp Business sender number on your own Twilio
   account (this includes Facebook Business Verification — allow days).
2. Register it via `/admin/whatsapp/setup` against a test tenant.
3. `export WHATSAPP_PROVIDER=twilio` and restart communications-service.
4. `ngrok http 8003` → copy the HTTPS forwarding URL.
5. In the Twilio Console, set the message-received webhook for the number to
   `<ngrok-url>/api/v1/whatsapp/webhooks/twilio/incoming` and the status
   callback to `.../status`. **Twilio will sign both with the auth_token of the
   account that owns the number** — that's the same token stored in
   `tenant_settings.whatsapp_twilio_token`, so signature verification will
   pass.
6. Text the business number "What documents do I have?" — expect a RAG reply
   in 5–15s.

---

## Verification checklist

- [ ] **Plan gating**: `setup` returns 403 on a Free-plan tenant, 200 on Pro+.
- [ ] **Phone uniqueness**: registering a phone already used by another
      tenant returns 409.
- [ ] **HMAC required**: a webhook with no `X-Twilio-Signature` returns 403.
- [ ] **Wrong-token HMAC rejected**: a webhook signed with the wrong tenant's
      token returns 403, no DB write.
- [ ] **Idempotency**: POSTing the same payload twice creates one
      `whatsapp_messages` row and produces one AI reply.
- [ ] **ACK latency**: inbound webhook consistently returns 200 in <1s.
- [ ] **Multi-tenant isolation**: a payload addressed to tenant B but signed
      with tenant A's token returns 403.
- [ ] **Disable cleanup**: `DELETE /admin/whatsapp/setup` clears all four
      tenant_settings columns and removes the `whatsapp_phone_mappings` row.

---

## Open follow-ups (not yet implemented)

- **Frontend admin form** — UI for the three-field setup. Lives in the
  frontend repo, not this backend.
- **Per-tenant rate limiting** — currently only the global webhook rate is
  bounded by RabbitMQ prefetch (5).
- **Audit publishing** — WhatsApp messages do not yet emit audit events.
- **Outbound proactive messaging API** — `WhatsAppService.send_whatsapp_message`
  is callable internally but not exposed via a tenant-facing endpoint.
- **Automated tests** — to be added under `communications-service/tests/`
  and `chat-service/tests/` as a follow-up (the original plan's Phase 10).
