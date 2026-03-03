# Per-Tenant Custom Limits for Enterprise Customers

## Context

The Enterprise plan currently stores `-1` (unlimited) for all usage limits in the database (seeded via Alembic migration `20251029_1330`). Each enterprise customer should have individually negotiated limits and pricing — there are no sensible "defaults" because every deal is different (small bank vs large bank vs very large bank). The Enterprise plan row in the `plans` table becomes a **tier marker** only; all actual limits and pricing come from a per-tenant configuration.

For self-serve plans (Free, Basic, Lite, Pro), limits continue to come from the `plans` table as today. The override table is optionally available for one-off adjustments but not required.

## Design: `TenantLimitOverride` Table

| Concept | Self-serve plans | Enterprise plan |
|---------|-----------------|-----------------|
| Limits source | `plans` table | `tenant_limit_overrides` table (required) |
| Override record | Optional (for courtesies) | **Mandatory** (created at subscription time) |
| Missing override | Falls back to plan defaults | **Blocked** — "Enterprise limits not configured" |
| Pricing | From `plans` table | From `tenant_limit_overrides` (custom per deal) |

## Bug Fix: `-1` Unlimited Convention

Current `subscription_checker.py` checks `usage.documents_used >= plan.document_limit` without handling `-1`. In Python, `0 >= -1` is `True`, so `-1` limits would **block** all usage. Fix: add explicit `-1` handling (treat as unlimited).

---

## Files to Create

### 1. `billing-service/app/models/tenant_limit_override.py`
New model:
- `id` (String(36), UUIDv4 PK)
- `tenant_id` (String(36), unique, indexed) — one record per tenant
- **Usage limits** (all `Integer, nullable=True`, NULL = use plan default):
  - `document_limit`, `website_limit`, `daily_chat_limit`, `monthly_chat_limit`
  - `max_document_size_mb`, `max_pages_per_website`
- **Custom pricing** (for enterprise deals):
  - `custom_monthly_cost` (Numeric(10,2), nullable=True)
  - `custom_yearly_cost` (Numeric(10,2), nullable=True)
- **Audit**:
  - `notes` (Text) — why this configuration exists (contract ref, deal terms)
  - `created_by`, `updated_by` (String(36))
- Standard timestamps (`created_at`, `updated_at`)

### 2. `billing-service/alembic/versions/20260303_add_tenant_limit_overrides.py`
Migration: create `tenant_limit_overrides` table. Chain after `20260224_0001`.

### 3. `billing-service/app/services/tenant_limit_service.py`
CRUD service:
- `create_override(tenant_id, limits, pricing, notes, admin_id)` — create override record
- `get_override(tenant_id)` — get raw override record
- `update_override(tenant_id, ...)` — update specific fields
- `delete_override(tenant_id)` — remove override (revert to plan defaults)
- `get_effective_limits(tenant_id, plan)` — resolve final limits (override → plan fallback)
  - For Enterprise: if no override exists, return `None` (signals enforcement to block)
  - For other plans: if no override, return plan defaults

### 4. `billing-service/app/api/tenant_limits.py`
Admin-only API (all require `require_system_admin`):
- `GET /api/v1/admin/tenant-limits/` — list all overrides (paginated)
- `GET /api/v1/admin/tenant-limits/{tenant_id}` — get override for tenant
- `POST /api/v1/admin/tenant-limits/{tenant_id}` — create override (all limit fields required for Enterprise tenants)
- `PUT /api/v1/admin/tenant-limits/{tenant_id}` — update override fields
- `DELETE /api/v1/admin/tenant-limits/{tenant_id}` — remove override
- `GET /api/v1/admin/tenant-limits/{tenant_id}/effective` — resolved limits with source attribution

### 5. `billing-service/tests/test_tenant_limit_overrides.py`

---

## Files to Modify

### 6. `billing-service/app/models/__init__.py`
Add `TenantLimitOverride` to imports and `__all__`.

### 7. `billing-service/alembic/env.py` (line 11)
Add `from app.models import tenant_limit_override`.

### 8. `billing-service/app/services/subscription_checker.py` — Core enforcement change

Add `_get_effective_limits(tenant_id, plan)` helper that:
1. Queries `TenantLimitOverride` for the tenant
2. If plan is Enterprise and no override exists → return `None` (caller blocks with clear message)
3. If override exists → merge: use override value when not NULL, fall back to plan value
4. If no override and not Enterprise → return plan values directly

Update each check method (`check_can_upload_document`, `check_can_ingest_website`, `check_can_send_chat`, `get_usage_summary`):
- Call `_get_effective_limits()`
- If returns `None` → return `(False, "Enterprise plan limits not configured for this tenant. Contact administrator.")`
- Add `-1` unlimited guard: `if limit is not None and limit != -1`
- Use effective limits instead of raw `plan.*` values

### 9. `billing-service/app/api/subscriptions.py` — Enterprise subscription creation
Modify `create_subscription` endpoint (line 437):
- After resolving the plan, if plan name is "Enterprise":
  - Require `enterprise_limits` in the request body (new optional field on `SubscriptionCreateRequest`)
  - Create `TenantLimitOverride` record with the provided limits
  - Fail with 400 if Enterprise plan selected but no limits provided

Add to `SubscriptionCreateRequest` schema (line 50):
```python
enterprise_limits: Optional[EnterpriseLimitsRequest] = Field(
    None, description="Required when subscribing to Enterprise plan"
)
```

New schema `EnterpriseLimitsRequest`:
```python
class EnterpriseLimitsRequest(BaseModel):
    document_limit: int
    website_limit: int
    daily_chat_limit: int
    monthly_chat_limit: int
    max_document_size_mb: int = 10
    max_pages_per_website: int = 100
    custom_monthly_cost: Decimal
    custom_yearly_cost: Decimal
    notes: Optional[str] = None
```

### 10. `billing-service/app/main.py` (line 23, after line 201)
Import and register `tenant_limits` router.

### 11. `billing-service/app/api/admin.py` (line 687)
Complete the existing `usage_limit_overrides` TODO: when `override_data.usage_limit_overrides` is provided, create/update a `TenantLimitOverride` record using `TenantLimitService`.

### 12. `billing-service/app/services/plan_service.py` (line 243-259)
Update `create_default_plans()` Enterprise entry: set limit fields to `0` (signals "must configure per tenant") instead of the current 1000/50/2000/60000. Description: "Custom solutions for large organizations — limits configured per tenant."

---

## Verification

1. Run `alembic upgrade head` to apply the migration
2. Try creating an Enterprise subscription **without** `enterprise_limits` → expect 400 error
3. Create an Enterprise subscription **with** `enterprise_limits` → succeeds, `TenantLimitOverride` record created
4. Hit restriction check endpoints → limits from override record are enforced
5. Create a Free/Basic/Pro subscription without limits → works as before (plan defaults)
6. Test the `/effective` endpoint shows source (override vs plan) for each field
7. Update override via admin API → restriction checks reflect new limits
8. Delete override for an Enterprise tenant → restriction checks block with "limits not configured"