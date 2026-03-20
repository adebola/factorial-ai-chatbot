# Integration Gateway Module for Banking Workflows

## Context

Banks demoing ChatCraft are most attracted to **chat banking** — conversational workflows where end users interact with banking backends after authentication. Key demands:
- 30+ intent-based workflows per tenant (and growing)
- OAuth2 authentication against the bank's own identity provider (various flows)
- Integration with legacy systems returning **XML, SOAP** — not just JSON
- Enterprise-grade reliability (retries, circuit breakers, audit trails)

The current `api_call_handler.py` (150 lines) only supports GET/POST, JSON/text, and simple token forwarding. It cannot handle what banks require.

**Decision**: Build as a **well-isolated module inside the workflow service** (`app/services/integration/`). This avoids the operational overhead of a new service while the banking use case is being validated. The module boundary is designed so it can be extracted into a standalone service later if scaling demands it.

## Architecture

```
User (WebSocket) → Chat Service (8000)
                      ↓
                   Workflow Service (8002)
                      ├── Orchestration (existing: execution, steps, triggers)
                      └── Integration Module (NEW: auth, protocols, resilience)
                             ↓
                          Bank REST / SOAP / XML / GraphQL APIs
```

The existing `ApiCallActionHandler` gains a branch: if `integration_slug` is present in action params, delegate to the Integration Module. Otherwise, keep existing direct-call behavior (zero breaking changes).

---

## 1. Module Structure

All new code lives under `workflow-service/app/services/integration/`:

```
workflow-service/app/services/integration/
  __init__.py
  proxy_service.py            # Main orchestrator: resolve → auth → call → transform → meter
  credential_service.py       # Encrypt/decrypt with Fernet (AES), key from env
  token_cache.py              # Redis cache for external OAuth2 tokens
  metering_service.py         # Publish usage events to billing via RabbitMQ
  audit_service.py            # Async audit log writes
  auth/
    __init__.py
    base.py                   # Abstract AuthProvider
    oauth2_cc.py              # Client Credentials flow
    oauth2_authcode.py        # Passthrough of user's bank token
    oauth2_token_exchange.py  # RFC 8693 token exchange
    api_key.py                # API key in header or query param
    basic.py                  # HTTP Basic Auth
    mtls.py                   # Mutual TLS (client certificates)
    custom_header.py          # Bank-specific custom headers
  protocols/
    __init__.py
    base.py                   # Abstract ProtocolHandler
    rest.py                   # REST/JSON — GET, POST, PUT, PATCH, DELETE
    soap.py                   # SOAP/XML — envelope wrapping, SOAPAction, fault handling
    xml_rest.py               # Plain XML REST APIs
    graphql.py                # GraphQL queries/mutations
  resilience/
    circuit_breaker.py        # Per-integration, Redis-backed (closed→open→half-open)
    retry.py                  # Exponential backoff with jitter, max 3 attempts
    rate_limiter.py           # Token bucket per-integration (Redis Lua script)
```

New API routes under `workflow-service/app/api/`:

```
workflow-service/app/api/
  integrations.py             # CRUD for integration configs (tenant-scoped)
  integration_admin.py        # Super-admin: health, audit log queries
```

New models under `workflow-service/app/models/`:

```
workflow-service/app/models/
  integration_model.py        # Integration registry + Credential + AuditLog
```

---

## 2. Data Models (workflow-service database)

### `integrations` — Per-tenant integration registry

| Column | Type | Purpose |
|--------|------|---------|
| `id` | String(36) PK | UUID |
| `tenant_id` | String(36), index | Tenant isolation |
| `name` | String(255) | Human label, e.g. "Core Banking API" |
| `slug` | String(100) | Used in workflow action params, e.g. "core-banking" |
| `description` | Text | Optional description |
| `protocol` | String(20) | `rest`, `soap`, `graphql`, `xml_rest` |
| `base_url` | String(2048) | e.g. `https://api.bank.com/v1` |
| `wsdl_url` | String(2048) | SOAP only |
| `auth_type` | String(30) | `oauth2_cc`, `oauth2_authcode`, `api_key`, `basic`, `mtls`, `custom_header`, `none` |
| `auth_config` | JSON | Non-secret auth config (token endpoint URL, scopes, key name/location) |
| `credential_id` | FK → credentials | Link to encrypted secrets |
| `environment` | String(20) | `sandbox` / `production` |
| `timeout_seconds` | Integer, default 30 | Per-integration timeout |
| `max_retries` | Integer, default 3 | Retry attempts |
| `circuit_breaker_threshold` | Integer, default 5 | Failures before opening circuit |
| `circuit_breaker_timeout` | Integer, default 60 | Seconds before half-open |
| `rate_limit_per_minute` | Integer, nullable | null = unlimited |
| `default_headers` | JSON | e.g. `{"X-Bank-Channel": "chatcraft"}` |
| `is_active` | Boolean | Soft toggle |
| `health_status` | String(20) | `healthy`, `degraded`, `down`, `unknown` |
| `created_at`, `updated_at` | DateTime | Timestamps |
| Unique: `(tenant_id, slug)` | | |

### `credentials` — Encrypted secrets

| Column | Type | Purpose |
|--------|------|---------|
| `id` | String(36) PK | UUID |
| `tenant_id` | String(36), index | Tenant isolation |
| `credential_type` | String(30) | Matches auth_type |
| `encrypted_data` | Text | Fernet-encrypted JSON blob |
| `last_rotated_at` | DateTime | Rotation tracking |
| `expires_at` | DateTime | Optional expiry |
| `created_at`, `updated_at` | DateTime | Timestamps |

**Encrypted data shapes by credential_type:**
- `oauth2_cc`: `{"client_id", "client_secret", "token_endpoint", "scopes"}`
- `api_key`: `{"key_value", "key_location": "header|query", "key_name": "X-Api-Key"}`
- `basic`: `{"username", "password"}`
- `mtls`: `{"cert_pem", "key_pem", "ca_pem"}`
- `custom_header`: `{"headers": {"X-Bank-Token": "..."}}`

Encryption key: `INTEGRATION_ENCRYPTION_KEY` env var (Fernet/AES-128-CBC). Never in config.py.

### `integration_audit_log` — Request/response trail

| Column | Type | Purpose |
|--------|------|---------|
| `id` | String(36) PK | |
| `tenant_id` | String(36), index | |
| `integration_id` | String(36), index | |
| `execution_id` | String(36), index | Workflow execution ID |
| `method` | String(10) | HTTP method used |
| `url` | String(2048) | Full URL called |
| `request_headers` | JSON | Sanitized (tokens → `[REDACTED]`) |
| `request_body_hash` | String(64) | SHA-256 hash only (PII compliance) |
| `status_code` | Integer | |
| `response_time_ms` | Integer | |
| `error_message` | Text | |
| `circuit_state` | String(20) | State at time of call |
| `attempt_number` | Integer | Which retry attempt |
| `created_at` | DateTime | |

---

## 3. Proxy Service Flow

The `ProxyService` is the central orchestrator — called by the refactored `ApiCallActionHandler`:

```
Request from ApiCallActionHandler
    ↓
1. Resolve Integration by (tenant_id, integration_slug)
    ↓
2. Circuit Breaker check → OPEN? return error immediately
    ↓
3. Rate Limiter check → exceeded? return 429 error
    ↓
4. Resolve Authentication
    ├── oauth2_cc → get/refresh client_credentials token from Redis cache
    ├── oauth2_authcode → use user_access_token from execution context
    ├── api_key → decrypt, inject into header/query
    ├── basic → decrypt username/password, set Authorization header
    ├── mtls → load cert/key into SSL context
    ├── custom_header → decrypt, merge into headers
    └── none → skip
    ↓
5. Build Protocol Request
    ├── rest → standard HTTP request
    ├── soap → wrap body in SOAP envelope, set SOAPAction header, Content-Type: text/xml
    ├── graphql → wrap in {"query": body, "variables": query_params}
    └── xml_rest → set Content-Type: application/xml
    ↓
6. Execute with Retry (exponential backoff + jitter, update circuit breaker on failure)
    ↓
7. Transform Response → always return JSON
    ├── JSON → pass through
    ├── XML → xmltodict.parse() → dict
    ├── SOAP → extract soap:Body → xmltodict.parse() → dict; raise on soap:Fault
    └── GraphQL → extract "data" field, raise on "errors"
    ↓
8. Audit Log (async fire-and-forget write)
    ↓
9. Meter API call (publish to RabbitMQ: usage.api_call.external)
    ↓
10. Return normalized result dict to ApiCallActionHandler
```

### Internal Interface

```python
# workflow-service/app/services/integration/proxy_service.py
class ProxyService:
    async def execute(
        self,
        tenant_id: str,
        integration_slug: str,
        method: str,
        path: str,
        headers: Optional[Dict] = None,
        query_params: Optional[Dict] = None,
        body: Optional[Any] = None,
        execution_id: Optional[str] = None,
        user_access_token: Optional[str] = None,
        response_format: str = "auto",
        xml_root_element: Optional[str] = None,
        timeout_override: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Returns {"success": bool, "status_code": int, "response_data": Any, ...}"""
```

This is the clean boundary — if the module is later extracted into a standalone service, `ProxyService.execute()` becomes an HTTP POST to `/api/v1/proxy/execute` with the same parameters.

---

## 4. Workflow Service Changes

### Refactor `ApiCallActionHandler`

**File**: `workflow-service/app/services/action_handlers/api_call_handler.py`

```python
async def execute(self, params, tenant_id, execution_id, variables, execution_context):
    if params.get("integration_slug"):
        # NEW: route through Integration Module
        return await self._call_via_integration(params, tenant_id, execution_id, execution_context)
    else:
        # EXISTING: direct HTTP call (unchanged, backward compatible)
        return await self._call_direct(params, tenant_id, execution_id, execution_context)
```

`_call_direct()` = current `execute()` body, moved as-is.
`_call_via_integration()` = instantiates `ProxyService` and calls `execute()`.

### New Workflow Action Params

When `integration_slug` is present, `url` is ignored (base URL comes from integration config):

```json
{
  "integration_slug": "core-banking",
  "path": "/accounts/{{account_number}}/balance",
  "method": "GET",
  "response_format": "auto",
  "forward_user_token": true
}
```

Existing workflows with `url` continue working unchanged.

---

## 5. Integration Management API

**File**: `workflow-service/app/api/integrations.py`

```
POST   /api/v1/integrations/                     # Create integration (tenant-scoped)
GET    /api/v1/integrations/                     # List tenant's integrations
GET    /api/v1/integrations/{slug}               # Get details
PUT    /api/v1/integrations/{slug}               # Update
DELETE /api/v1/integrations/{slug}               # Soft-delete

POST   /api/v1/integrations/{slug}/credentials   # Set/rotate credentials
DELETE /api/v1/integrations/{slug}/credentials   # Remove credentials
POST   /api/v1/integrations/{slug}/test          # Test connection (health check call)
POST   /api/v1/integrations/{slug}/promote       # Sandbox → Production
```

**File**: `workflow-service/app/api/integration_admin.py`

```
GET    /api/v1/admin/integrations/health         # Super-admin: all integrations health
GET    /api/v1/admin/integrations/audit-log      # Super-admin: query audit logs
```

Add routes to Spring Cloud Gateway `application.yml`:
```yaml
- id: integration-management
  uri: http://localhost:8002
  predicates:
    - Path=/api/v1/integrations/**
- id: integration-admin
  uri: http://localhost:8002
  predicates:
    - Path=/api/v1/admin/integrations/**
```

---

## 6. Token Caching for External OAuth2

Redis key pattern (follows existing `session_auth_service.py` pattern):
```
ext_token:{tenant_id}:{integration_id}
```
Value: `{"access_token": "...", "expires_at": epoch}`
TTL: token expiry minus 60s buffer.

- `oauth2_cc`: Gateway acquires and caches tokens itself via client_credentials grant.
- `oauth2_authcode`: User's bank token passed through from workflow execution context (already stored in Redis by `session_auth_service.py`).

---

## 7. Resilience Details

### Circuit Breaker (Redis-backed, per-integration)
Key: `circuit:{tenant_id}:{integration_id}`
- **CLOSED**: Normal. Track consecutive failures. When `failure_count >= threshold` → OPEN.
- **OPEN**: All calls fail immediately with error. After `circuit_breaker_timeout` seconds → HALF_OPEN.
- **HALF_OPEN**: Allow one call. Success → CLOSED (reset). Failure → OPEN.

### Retry
Exponential backoff with jitter: `delay = min(2^attempt + random(0,1), 30s)`. Max attempts from `integration.max_retries`. Only retry on 5xx or connection errors, never on 4xx.

### Rate Limiter
Token bucket algorithm via Redis Lua script. Configured per-integration via `rate_limit_per_minute`.

---

## 8. Billing & Metering Extensions

### New Plan Columns
**File**: `billing-service/app/models/plan.py`

| Column | Type | Default | Purpose |
|--------|------|---------|---------|
| `workflow_limit` | Integer | 5 | Max active workflows (-1 = unlimited) |
| `integration_limit` | Integer | 1 | Max configured integrations |
| `external_api_call_limit` | Integer | 1000 | Max external API calls/month |
| `workflow_execution_limit` | Integer | 5000 | Max workflow executions/month |

### New Usage Tracking Columns
**File**: `billing-service/app/models/subscription.py` (UsageTracking model)

| Column | Type | Purpose |
|--------|------|---------|
| `workflows_active` | Integer | Current active workflow count |
| `integrations_active` | Integer | Current configured integrations |
| `api_calls_external` | Integer | External API calls this period |
| `workflow_executions` | Integer | Workflow runs this period |

### RabbitMQ Metering Events

| Routing Key | Published By | Data |
|---|---|---|
| `usage.api_call.external` | Integration Module (workflow svc) | `{tenant_id, integration_id, status_code, response_time_ms}` |
| `usage.workflow.execution` | Workflow Service (execution_service) | `{tenant_id, workflow_id}` |
| `usage.workflow.activated` | Workflow Service (workflow CRUD) | `{tenant_id, workflow_id}` |

### Suggested Plan Tiers for Banking

| | Free | Basic | Pro | Enterprise |
|---|---|---|---|---|
| Active Workflows | 2 | 5 | 30 | Unlimited |
| Integrations | 1 | 3 | 10 | Unlimited |
| Ext API Calls/mo | 100 | 1,000 | 10,000 | Unlimited |
| Workflow Runs/mo | 500 | 5,000 | 50,000 | Unlimited |
| Auth Types | API Key | + OAuth2 CC | + All OAuth2 | + mTLS |
| SOAP/XML | No | No | Yes | Yes |
| Audit Retention | 7 days | 30 days | 90 days | 365 days |

---

## 9. Security Considerations

1. **Credential isolation**: Every DB query includes `tenant_id`. No cross-tenant credential access.
2. **Audit sanitization**: Auth tokens → `[REDACTED]` in logs. Request bodies hashed (SHA-256), not stored raw — PII compliance for banking data flowing through the system.
3. **Token passthrough**: User's bank access token flows in execution context, used for one call, never persisted by the integration module.
4. **mTLS certs**: Stored encrypted. Loaded into ephemeral `ssl.SSLContext` per-request.
5. **Encryption key rotation**: Support re-encryption of all credentials when `INTEGRATION_ENCRYPTION_KEY` is rotated.

---

## 10. Phased Implementation

### Phase 1 — Bank Demo Ready (~2-3 weeks)
**Goal**: REST/JSON + OAuth2 Client Credentials + API Key auth, basic retry. Enough for bank demos.

1. Create `workflow-service/app/services/integration/` module structure
2. `Integration` and `Credential` models + Alembic migration (workflow-service DB)
3. `ProxyService` with REST protocol handler
4. `oauth2_cc` and `api_key` auth providers
5. `CredentialService` with Fernet encryption/decryption
6. Basic retry (3 attempts, exponential backoff)
7. Refactor `ApiCallActionHandler` — add `integration_slug` branch
8. Integration CRUD API endpoints (`/api/v1/integrations/`)
9. Connection test endpoint
10. Support all HTTP methods (GET, POST, PUT, PATCH, DELETE)
11. Add gateway routes in Spring Cloud Gateway `application.yml`
12. Add `xmltodict`, `cryptography` to `workflow-service/requirements.txt`

### Phase 2 — XML/SOAP + Resilience (~2 weeks)
1. XML response transformer (`xmltodict`)
2. SOAP protocol handler (envelope wrapping, SOAPAction, fault handling)
3. Circuit breaker (Redis-backed)
4. Rate limiter (token bucket)
5. `integration_audit_log` table + async audit writes
6. Health check per integration

### Phase 3 — Advanced Auth + Billing (~2 weeks)
1. OAuth2 Token Exchange (RFC 8693) auth provider
2. Basic Auth, mTLS, Custom Header providers
3. New billing plan columns + Alembic migration
4. New usage tracking columns + Alembic migration
5. RabbitMQ metering events from integration module
6. Billing service consumer handlers for new event types
7. Billing enforcement gates (check limits before proxy execution)

### Phase 4 — GraphQL + Polish (~1 week)
1. GraphQL protocol handler
2. Sandbox/production environment promotion
3. Credential rotation tracking
4. Admin health dashboard + audit log query endpoints

---

## 11. Future Extraction Path

When scaling demands it, the integration module can be extracted into a standalone service:
1. Move `workflow-service/app/services/integration/` → `integration-gateway-service/app/services/`
2. Move `Integration`, `Credential`, `IntegrationAuditLog` models → new service DB
3. `ProxyService.execute()` → exposed as `POST /api/v1/proxy/execute` HTTP endpoint
4. `ApiCallActionHandler._call_via_integration()` changes from in-process call to HTTP call
5. The interface contract (`ProxyService.execute()` params) stays identical

---

## 12. Key Files to Modify

| File | Change |
|------|--------|
| `workflow-service/app/services/action_handlers/api_call_handler.py` | Add `integration_slug` branch; `_call_via_integration()` delegates to `ProxyService` |
| `workflow-service/app/services/integration/` (NEW) | Entire integration module |
| `workflow-service/app/models/integration_model.py` (NEW) | Integration, Credential, IntegrationAuditLog models |
| `workflow-service/app/api/integrations.py` (NEW) | CRUD + test + promote endpoints |
| `workflow-service/app/api/integration_admin.py` (NEW) | Super-admin health + audit endpoints |
| `workflow-service/alembic/versions/` (NEW) | Migration for integrations, credentials, audit_log tables |
| `workflow-service/requirements.txt` | Add `xmltodict`, `cryptography` (for Fernet) |
| `billing-service/app/models/plan.py` | Add `workflow_limit`, `integration_limit`, `external_api_call_limit`, `workflow_execution_limit` |
| `billing-service/app/models/subscription.py` | Add usage tracking columns to `UsageTracking` |
| `billing-service/alembic/versions/` (NEW) | Migration for new plan + usage columns |
| `gateway-service/src/main/resources/application.yml` | Add routes for `/api/v1/integrations/**` and `/api/v1/admin/integrations/**` |

## 13. Verification

1. **Phase 1 smoke test**: Create an integration (REST + API key), create workflow with `integration_slug` ACTION step, trigger via chat → verify response flows through proxy service
2. **Backward compat**: Existing workflows with `url` param still work without integration module
3. **Credential security**: Verify credentials are encrypted in DB, decrypted only at call time, never logged
4. **SOAP test (Phase 2)**: Configure SOAP integration, trigger workflow → verify XML→JSON transform returns clean dict
5. **Circuit breaker (Phase 2)**: Point integration at dead endpoint, trigger 5+ times → verify calls fail fast after threshold
6. **Billing (Phase 3)**: Trigger integration calls → verify `api_calls_external` increments in usage tracking