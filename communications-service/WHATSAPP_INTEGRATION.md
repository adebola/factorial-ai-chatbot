# WhatsApp Integration Implementation Plan

## Overview

Add WhatsApp messaging capability to ChatCraft, allowing customers to interact with their AI chatbot via WhatsApp using the same RAG pipeline as the web interface.

**Provider:** Twilio WhatsApp Business API
**Tenant Model:** Hybrid - tenants can use their own WhatsApp number OR system-assigned shared number
**MVP Scope:** Text messaging only with conversation context/session management

---

## Architecture Decision

**Service Ownership: Communications Service** (Port 8003)

**Rationale:**
- Leverages existing Twilio SMS infrastructure
- Follows established webhook pattern (like Paystack)
- Maintains separation of concerns (delivery vs AI logic)

**Message Flow:**
```
WhatsApp User → Twilio Webhook → Communications Service
                                    ↓ (verify signature, resolve tenant)
                                    ↓ (store message, get/create session)
                                    ↓
                            HTTP Call to Chat Service REST API
                                    ↓ (RAG pipeline: vector search + OpenAI)
                                    ↓ (returns AI response)
                                    ↓
                          Send response via Twilio WhatsApp API
                                    ↓
                          Track delivery status via webhook
```

---

## Database Changes

### 1. Extend `TenantSettings` Model

**File:** `communications-service/app/models/communications.py`

Add WhatsApp configuration fields:
- `whatsapp_enabled: Boolean` - Whether WhatsApp is active for tenant
- `whatsapp_mode: String(20)` - 'shared' or 'own'
- `whatsapp_twilio_sid: String(255)` - Encrypted Twilio account SID (for 'own' mode)
- `whatsapp_twilio_token: String(255)` - Encrypted auth token (for 'own' mode)
- `whatsapp_phone_number: String(20)` - WhatsApp Business phone number
- `shared_whatsapp_assigned: Boolean` - If using system's shared number

### 2. New `WhatsAppMessage` Model

Tracks all WhatsApp messages (inbound and outbound):
- Links to chat sessions via `chat_session_id`
- Stores delivery status and timestamps
- Tracks Twilio message SIDs for status updates

### 3. New `WhatsAppPhoneMapping` Model

Maps WhatsApp business phone numbers to tenants:
- `business_phone_number` → `tenant_id`
- `is_shared_number` flag for system-assigned numbers
- Unique constraint on (tenant_id, business_phone_number)

**Migration:** `alembic/versions/YYYYMMDD_add_whatsapp_support.py`

---

## New Components

### 1. WhatsApp Provider (`services/whatsapp_provider.py`)

Abstract provider interface with implementations:
- `TwilioWhatsAppProvider` - Uses Twilio SDK for sending
- `MockWhatsAppProvider` - For testing without Twilio

**Key Method:** `send_whatsapp_message(to, from, message)` → (message_id, success, error)

### 2. WhatsApp Service (`services/whatsapp_service.py`)

Core business logic:
- `resolve_tenant_from_phone()` - Map incoming phone → tenant_id
- `handle_incoming_message()` - Main webhook handler logic
- `send_whatsapp_message()` - Send outbound messages
- `handle_delivery_status()` - Process Twilio status callbacks
- `_generate_ai_response()` - Call Chat Service REST API

### 3. Webhook API (`api/whatsapp.py`)

FastAPI routes:
- `POST /webhooks/twilio/whatsapp/incoming` - Receive messages from Twilio
- `POST /webhooks/twilio/whatsapp/status` - Delivery status callbacks
- `POST /admin/whatsapp/setup` - Tenant WhatsApp configuration

**Security:** HMAC-SHA1 signature verification using `X-Twilio-Signature` header

### 4. Chat Service REST Endpoint (`chat-service/app/api/chat_api.py`)

New endpoint for non-WebSocket channels:
- `POST /api/v1/chat/generate` - Generate AI response via REST
- Uses existing `ChatService.generate_response()` RAG pipeline
- Returns response content, sources, metadata

---

## Configuration

### Environment Variables

**communications-service/.env:**
```bash
# Existing Twilio (already present for SMS)
TWILIO_ACCOUNT_SID=ACxxxxx
TWILIO_AUTH_TOKEN=xxxxx

# WhatsApp specific (NEW)
WHATSAPP_PROVIDER=twilio  # or 'mock' for testing
WHATSAPP_FROM_PHONE=+14155238886  # Sandbox number for testing
WHATSAPP_ENABLED=true

# Chat service endpoint (NEW)
CHAT_SERVICE_URL=http://localhost:8000

# Credential encryption (NEW)
CREDENTIAL_ENCRYPTION_KEY=<fernet-key>
```

**chat-service/.env:**
No changes needed - existing setup sufficient

### Twilio Setup (Development)

1. Use Twilio WhatsApp Sandbox for testing
2. Join sandbox: Send `join <keyword>` to sandbox number
3. Configure webhook URLs in Twilio Console:
    - Incoming: `https://<ngrok-url>/api/v1/whatsapp/webhooks/twilio/whatsapp/incoming`
    - Status: `https://<ngrok-url>/api/v1/whatsapp/webhooks/twilio/whatsapp/status`

**Production:** Apply for WhatsApp Business API access through Twilio

---

## Implementation Steps

### Phase 1: Database Foundation (Day 1)
1. ✅ Create Alembic migration `YYYYMMDD_add_whatsapp_support.py`
2. ✅ Add WhatsApp models to `communications.py`
3. ✅ Run migration: `alembic upgrade head`
4. ✅ Test model creation and queries

### Phase 2: Core Services (Days 2-3)
1. ✅ Create `whatsapp_provider.py` with Twilio + Mock providers
2. ✅ Create `whatsapp_service.py` with business logic
3. ✅ Implement tenant resolution from phone number
4. ✅ Implement session management (reuse chat session pattern)
5. ✅ Write unit tests for providers and service

### Phase 3: Webhook Handlers (Day 4)
1. ✅ Create `api/whatsapp.py` router
2. ✅ Implement incoming message webhook endpoint
3. ✅ Implement Twilio signature verification
4. ✅ Implement delivery status webhook
5. ✅ Add to `main.py`: `app.include_router(whatsapp.router, prefix="/api/v1/whatsapp")`

### Phase 4: Chat Service Integration (Day 5)
1. ✅ Create `chat-service/app/api/chat_api.py`
2. ✅ Add `POST /chat/generate` REST endpoint
3. ✅ Integrate with existing `ChatService.generate_response()`
4. ✅ Add router to chat service `main.py`
5. ✅ Test end-to-end: WhatsApp → webhook → chat → response

### Phase 5: Admin Management (Day 6)
1. ✅ Add `/admin/whatsapp/setup` endpoint to configure tenant
2. ✅ Implement phone number assignment logic
3. ✅ Add credential encryption for tenant Twilio credentials
4. ✅ Test tenant onboarding flow (both modes)

### Phase 6: Testing & Deployment (Day 7)
1. ✅ Integration tests with Twilio sandbox
2. ✅ Test multi-tenant scenarios
3. ✅ Test error handling (invalid signatures, failed sends)
4. ✅ Update API documentation
5. ✅ Deploy to staging environment

---

## Critical Files to Modify

### Communications Service
- `app/models/communications.py` - Add WhatsApp models
- `app/services/whatsapp_provider.py` - NEW file
- `app/services/whatsapp_service.py` - NEW file
- `app/api/whatsapp.py` - NEW file
- `app/main.py` - Register WhatsApp router
- `alembic/versions/YYYYMMDD_add_whatsapp_support.py` - NEW migration
- `.env` - Add WhatsApp config variables
- `requirements.txt` - Add `twilio` if not present

### Chat Service
- `app/api/chat_api.py` - NEW file for REST endpoint
- `app/main.py` - Register chat API router

---

## Testing Strategy

### Unit Tests
- `tests/test_whatsapp_provider.py` - Test Twilio provider methods
- `tests/test_whatsapp_service.py` - Test business logic
- Mock external dependencies (Twilio API, Chat Service)

### Integration Tests
- `tests/integration/test_whatsapp_flow.py`
- Use Twilio sandbox for real webhook tests
- Test signature verification
- Test complete message flow

### Manual Testing Checklist
- [ ] Send WhatsApp message to sandbox number
- [ ] Verify incoming webhook received and processed
- [ ] Verify tenant resolved correctly
- [ ] Verify AI response generated
- [ ] Verify response sent back to WhatsApp
- [ ] Verify delivery status tracked
- [ ] Test with multiple tenants (shared vs own mode)
- [ ] Test error scenarios (invalid signature, unknown tenant)

---

## Deployment Requirements

### Infrastructure
- **HTTPS Required:** Twilio webhooks require SSL
- **Local Dev:** Use ngrok for tunnel: `ngrok http 8003`
- **Production:** Ensure public HTTPS endpoint with valid SSL certificate

### Service Dependencies
Startup order:
1. PostgreSQL, Redis, RabbitMQ
2. Authorization Server
3. Chat Service (must be available for REST calls)
4. Communications Service (webhooks ready)

### Security
- Encrypt tenant Twilio credentials in database
- Validate Twilio webhook signatures (HMAC-SHA1)
- Use environment-specific encryption keys
- Implement rate limiting for webhook endpoints

---

## Verification Steps

### End-to-End Test Flow

1. **Setup:**
   ```bash
   # Start services
   cd communications-service && uvicorn app.main:app --port 8003 --reload
   cd chat-service && uvicorn app.main:app --port 8000 --reload

   # Start ngrok
    ngrok http 8003
   ```

2. **Configure Twilio:**
    - Update webhook URL in Twilio Console with ngrok HTTPS URL
    - Join WhatsApp sandbox

3. **Test Message Flow:**
    - Send WhatsApp message: "Hello"
    - Check logs for incoming webhook
    - Verify tenant resolution
    - Verify Chat Service called
    - Verify AI response sent back
    - Check WhatsApp for response

4. **Verify Database:**
   ```sql
   -- Check message stored
   SELECT * FROM whatsapp_messages ORDER BY created_at DESC LIMIT 5;

   -- Check tenant mapping
   SELECT * FROM whatsapp_phone_mappings;

   -- Check delivery status
   SELECT status, delivered_at FROM whatsapp_messages WHERE direction='outbound';
   ```

5. **Test Admin Setup:**
   ```bash
   # Setup tenant with shared number
   curl -X POST http://localhost:8003/api/v1/whatsapp/admin/whatsapp/setup \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{"mode": "shared"}'
   ```

---

## Future Enhancements (Post-MVP)

- Media support (images, documents, audio)
- WhatsApp message templates (business-initiated messages)
- Advanced session management (smart timeouts)
- Multi-number support per tenant
- Analytics dashboard for WhatsApp conversations
- Quick replies and interactive buttons

---

## Success Criteria

- ✅ Users can send WhatsApp messages and receive AI responses
- ✅ Conversation context maintained across messages (session management)
- ✅ Tenants can use their own WhatsApp Business number
- ✅ Tenants without their own number can use shared system number
- ✅ All messages logged with delivery status
- ✅ Webhook security properly implemented
- ✅ Integration with existing RAG pipeline working
- ✅ Multi-tenant isolation maintained


