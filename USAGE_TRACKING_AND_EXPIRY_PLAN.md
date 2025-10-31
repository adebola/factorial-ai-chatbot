# Usage Tracking, Feature Enforcement, and Subscription Expiry Implementation Plan

**Created**: 2025-01-17
**Status**: Planning Phase

---

## Current State Analysis

### ✅ What EXISTS:
1. **Usage Tracking Infrastructure**:
   - UsageTracking model with counters (documents_used, websites_used, daily_chats_used, monthly_chats_used)
   - UsageService in onboarding-service with check/increment methods
   - Plan model with limits (document_limit, website_limit, daily_chat_limit, monthly_chat_limit)

2. **Feature Flags Infrastructure**:
   - Plan model has feature flags (has_sentiment_analysis, has_conversational_workflow, has_api_access, etc.)
   - Feature flag middleware decorators (@require_feature, @require_any_feature, @require_all_features)
   - BillingClient for inter-service communication

3. **Subscription Model**:
   - SubscriptionStatus.EXPIRED exists
   - Subscription has ends_at, grace_period_ends_at fields
   - auto_renew flag (but manual payment required per Paystack constraints)

### ❌ What's MISSING:

1. **Usage API Endpoints** - BillingClient references `/api/v1/usage/*` endpoints that don't exist
2. **Chat Service Integration** - No usage enforcement for daily/monthly chat limits
3. **Onboarding Service Integration** - No usage checks before document upload or website scraping
4. **Subscription Expiry Handler** - No scheduled job to mark subscriptions as EXPIRED
5. **Manual Renewal Flow** - No API endpoint for renewing expired subscriptions
6. **Feature Flag Enforcement** - Decorators exist but not applied to any endpoints
7. **Grace Period Logic** - No handling of expired subscriptions with grace periods

---

## Design Principle: Async-First Architecture

**⚠️ IMPORTANT**: Prefer async messaging (RabbitMQ) over synchronous REST API calls wherever possible to:
- Reduce coupling between services
- Improve resilience (services can be temporarily down)
- Enable event-driven architecture
- Reduce latency for user-facing operations

**When to use REST API**:
- Real-time checks needed for user operations (e.g., checking usage limit before allowing action)
- Simple synchronous queries (e.g., get plan details)

**When to use RabbitMQ**:
- Usage increment notifications (fire-and-forget)
- Subscription state changes
- Notifications to users
- Background processing
- Cross-service updates

---

## Implementation Plan

### Phase 1: Usage API Endpoints (billing-service)
**Create**: `app/api/usage.py`

**Endpoints**:
- `GET /api/v1/usage/check-limit/{usage_type}` - Check if usage is allowed (**Synchronous** - real-time decision needed)
- `POST /api/v1/usage/increment` - Increment usage counter (**Keep for backward compatibility, but prefer RabbitMQ**)
- `GET /api/v1/usage/statistics` - Get comprehensive usage stats (**Synchronous**)
- `GET /api/v1/usage/summary` - Get dashboard summary (**Synchronous**)
- `POST /api/v1/usage/reset-daily` - Admin: Reset daily counters
- `POST /api/v1/usage/reset-monthly` - Admin: Reset monthly counters

**Create**: `app/services/usage_service.py` (copy from onboarding-service + enhancements)

**Create**: `app/messaging/usage_consumer.py` - **NEW: RabbitMQ Consumer for usage events**

**RabbitMQ Events** (Exchange: `usage.events`, Type: topic):
- `usage.increment.documents` - Document uploaded
- `usage.increment.websites` - Website scraped
- `usage.increment.chat.daily` - Daily chat message sent
- `usage.increment.chat.monthly` - Monthly chat message sent
- `usage.increment.api_calls` - API call made

**Message Format**:
```json
{
  "event_type": "usage_increment",
  "tenant_id": "uuid",
  "usage_type": "daily_chats",
  "amount": 1,
  "timestamp": "2025-01-17T10:30:00Z",
  "metadata": {
    "source_service": "chat-service",
    "session_id": "...",
    "user_id": "..."
  }
}
```

**Update**: `app/main.py` to include usage router and start RabbitMQ consumer

---

### Phase 2: Chat Service Usage Enforcement
**Update**: `chat-service/app/websocket/chat_handler.py` (or relevant handler)

**Changes**:
1. **Before processing chat message** (**Synchronous check required**):
   - Call BillingClient.check_usage_limit("daily_chats")
   - Call BillingClient.check_usage_limit("monthly_chats")
   - If either limit exceeded, return error message to user

2. **After successful chat response** (**Async via RabbitMQ**):
   - Publish to RabbitMQ: `usage.increment.chat.daily`
   - Publish to RabbitMQ: `usage.increment.chat.monthly`
   - **DO NOT** wait for response, fire-and-forget
   - If RabbitMQ publish fails, log error but don't block user

**Add**: `chat-service/app/services/billing_client.py` (for synchronous limit checks only)
**Add**: `chat-service/app/messaging/usage_publisher.py` (for async usage increments)

**Add**: `chat-service/app/services/rabbitmq_publisher.py` (if not exists)

---

### Phase 3: Onboarding Service Usage Enforcement
**Update**: `onboarding-service/app/api/documents.py`

**Changes**:
1. **Before document upload** (**Synchronous check required**):
   - Check documents_used < document_limit via BillingClient
   - Check document size <= max_document_size_mb
   - If limit exceeded, reject upload immediately

2. **After successful upload** (**Async via RabbitMQ**):
   - Publish to RabbitMQ: `usage.increment.documents`
   - Fire-and-forget, don't block user response

**Update**: `onboarding-service/app/api/websites.py`

**Changes**:
1. **Before website scraping** (**Synchronous check required**):
   - Check websites_used < website_limit via BillingClient

2. **After successful scrape** (**Async via RabbitMQ**):
   - Publish to RabbitMQ: `usage.increment.websites`

**Add**: `onboarding-service/app/messaging/usage_publisher.py`

---

### Phase 4: Subscription Expiry Handling
**Create**: `billing-service/app/services/subscription_expiry_service.py`

**Methods**:
- `check_expired_subscriptions()` - Find subscriptions where ends_at < now and status != EXPIRED
- `expire_subscription(subscription_id)` - Set status to EXPIRED, **publish event to RabbitMQ**
- `check_trial_expirations()` - Find TRIALING subscriptions where trial_ends_at < now
- `process_pending_downgrades()` - Apply pending plan changes when effective_date reached

**Create**: `billing-service/app/scheduler/subscription_tasks.py`

**Scheduled Tasks** (using APScheduler or similar):
- Every hour: Check for expired subscriptions
- Every hour: Check for expired trials
- Every hour: Process pending downgrades
- Daily at midnight: Reset daily usage counters

**RabbitMQ Events** (Exchange: `subscription.events`, Type: topic):
- `subscription.expired` - Subscription has expired
- `subscription.trial_expired` - Trial period ended
- `subscription.grace_period_started` - Grace period began
- `subscription.grace_period_expired` - Grace period ended, full expiry
- `subscription.renewed` - Subscription was renewed
- `subscription.downgraded` - Scheduled downgrade applied
- `subscription.upgraded` - Subscription upgraded

**Message Format**:
```json
{
  "event_type": "subscription_expired",
  "tenant_id": "uuid",
  "subscription_id": "uuid",
  "plan_id": "uuid",
  "plan_name": "Basic",
  "expired_at": "2025-01-17T10:30:00Z",
  "grace_period_ends_at": "2025-01-20T10:30:00Z",
  "previous_status": "active",
  "new_status": "expired"
}
```

**Consumers of these events**:
- **Authorization Server**: Update tenant status/plan_id
- **Communications Service**: Send email notifications
- **Chat Service**: Invalidate cache, block new sessions
- **Onboarding Service**: Block uploads/scraping

**Update**: `billing-service/app/main.py` - Start scheduler on app startup

---

### Phase 5: Manual Renewal Flow
**Create endpoints in** `billing-service/app/api/subscriptions.py`:

1. `POST /api/v1/subscriptions/renew` - Renew expired subscription (**Synchronous** - user needs payment URL)
   - Check subscription is EXPIRED
   - Create new subscription period (30 days or 365 days based on billing_cycle)
   - Initialize Paystack payment
   - Return payment URL

2. `GET /api/v1/subscriptions/renewal-info` - Get renewal information (**Synchronous**)
   - Return current plan, amount to pay, renewal period

3. `POST /api/v1/subscriptions/verify-renewal/{reference}` - Verify renewal payment (**Synchronous** with **Async notifications**)
   - Verify Paystack payment
   - Update subscription: status = ACTIVE, starts_at = now, ends_at = now + period
   - Reset usage counters
   - **Publish to RabbitMQ**: `subscription.renewed` event
   - **Async**: Authorization server will listen and update tenant
   - **Async**: Communications service will send confirmation email
   - **Async**: Other services will invalidate caches

---

### Phase 6: Expired Subscription Enforcement
**Create**: `billing-service/app/middleware/subscription_guard.py`

**Middleware**:
- Check if tenant's subscription is EXPIRED
- Block all API calls except:
  - /health
  - /api/v1/plans/* (read-only to see upgrade options)
  - /api/v1/subscriptions/renew
  - /api/v1/subscriptions/renewal-info
  - /api/v1/subscriptions/verify-renewal

**Apply to**:
- Chat service endpoints
- Onboarding service endpoints (document/website operations)
- Workflow service endpoints

**Implementation Options**:
1. **Option A (Recommended)**: Each service subscribes to `subscription.expired` events and caches tenant status
2. **Option B**: Each service checks billing-service on every request (higher latency)
3. **Option C**: API Gateway checks billing-service and blocks requests centrally

**Recommended: Option A with Redis cache**:
- Billing service publishes `subscription.expired`
- Each service listens and updates Redis: `tenant:{tenant_id}:subscription_status`
- Each service checks Redis cache (fast, O(1))
- Cache TTL: 5 minutes (automatically refreshes from events)

---

### Phase 7: Feature Flag Enforcement
**Apply decorators to endpoints**:

**Workflow Service** (when sentiment analysis/workflow features are built):
```python
@router.post("/workflow/conversational")
@require_feature(FeatureFlag.CONVERSATIONAL_WORKFLOW)
async def create_conversational_workflow(...)

@router.post("/sentiment/analyze")
@require_feature(FeatureFlag.SENTIMENT_ANALYSIS)
async def analyze_sentiment(...)
```

**API Access Endpoints**:
```python
@router.get("/api/external/*")
@require_feature(FeatureFlag.API_ACCESS)
async def external_api(...)
```

**Create**: `billing-service/app/api/features.py` - Feature discovery endpoint
- `GET /api/v1/features` - Return tenant's available features (**Synchronous**)
- `GET /api/v1/features/check/{feature_name}` - Check if tenant has specific feature (**Synchronous**)

**Optimization**: Cache feature flags in Redis, subscribe to `subscription.plan_changed` events to invalidate

---

### Phase 8: Grace Period Implementation
**Update**: `billing-service/app/services/subscription_expiry_service.py`

**Logic**:
1. When subscription expires (ends_at < now):
   - If grace_period_ends_at is NULL → Set grace_period_ends_at = now + 3 days
   - Status remains ACTIVE during grace period
   - **Publish to RabbitMQ**: `subscription.grace_period_started`
   - Communications service sends "subscription expiring" email

2. When grace period expires (grace_period_ends_at < now):
   - Set status = EXPIRED
   - **Publish to RabbitMQ**: `subscription.grace_period_expired`
   - Block all operations except renewal
   - Communications service sends "subscription expired" email

**Benefits**:
- Gives users 3 days to renew after subscription ends
- Prevents immediate service interruption
- Industry-standard practice

---

### Phase 9: Notifications System
**Create**: `billing-service/app/services/notification_service.py`

**Publishes notification events to RabbitMQ** (Exchange: `notification.events`, Type: topic):

**Notification Types**:
1. **7 days before expiry**: `notification.subscription.expiring.7days`
2. **3 days before expiry**: `notification.subscription.expiring.3days`
3. **1 day before expiry**: `notification.subscription.expiring.1day`
4. **On expiry**: `notification.subscription.expired`
5. **Grace period started**: `notification.subscription.grace_period_started`
6. **Grace period ending (1 day)**: `notification.subscription.grace_period_ending`
7. **Usage warnings (80%)**: `notification.usage.warning.80percent`
8. **Usage warnings (95%)**: `notification.usage.warning.95percent`
9. **Usage limit reached**: `notification.usage.limit_reached`
10. **Subscription renewed**: `notification.subscription.renewed`

**Message Format**:
```json
{
  "event_type": "notification.subscription.expiring.3days",
  "tenant_id": "uuid",
  "notification_type": "subscription_expiring",
  "severity": "warning",
  "channels": ["email", "in_app"],
  "data": {
    "subscription_id": "uuid",
    "plan_name": "Basic",
    "expires_at": "2025-01-20T10:30:00Z",
    "days_remaining": 3,
    "renewal_url": "https://app.example.com/billing/renew"
  },
  "template": "subscription_expiring_3days",
  "timestamp": "2025-01-17T10:30:00Z"
}
```

**Communications Service Consumer**:
- Listens to `notification.*` events
- Sends emails via SendGrid/Mailgun
- Stores in-app notifications in database
- Sends push notifications (future)

**Scheduled Checks** (in subscription_tasks.py):
- Daily at 9 AM: Check subscriptions expiring in 7 days
- Daily at 9 AM: Check subscriptions expiring in 3 days
- Daily at 9 AM: Check subscriptions expiring in 1 day

---

## RabbitMQ Exchange and Queue Design

### Exchanges:
1. **usage.events** (topic)
   - Routing keys: `usage.increment.{usage_type}`
   - Consumer: billing-service/usage_consumer.py

2. **subscription.events** (topic)
   - Routing keys: `subscription.{event_type}`
   - Consumers:
     - authorization-server (update tenant status)
     - communications-service (send notifications)
     - chat-service (invalidate cache)
     - onboarding-service (invalidate cache)
     - workflow-service (invalidate cache)

3. **notification.events** (topic)
   - Routing keys: `notification.{notification_type}`
   - Consumer: communications-service/notification_consumer.py

### Queue Naming Convention:
- `{service_name}.{exchange_name}.{routing_key_pattern}`
- Examples:
  - `billing-service.usage.events.#`
  - `authorization-server.subscription.events.#`
  - `communications-service.notification.events.#`

### Dead Letter Queues (DLQs):
- All queues should have DLQs for failed message handling
- DLQ naming: `{queue_name}.dlq`
- Monitor DLQs for failed events

---

## Subscription Expiry Enforcement Strategy

### **Recommended Approach** (Given Manual Payment Requirement):

1. **Soft Expiry with Grace Period** (3 days):
   - Status: ACTIVE → grace period → EXPIRED
   - During grace: Limited access + prominent renewal banner
   - After grace: Complete service block except renewal flow

2. **What Happens When Subscription Expires**:
   - **During Grace Period** (3 days):
     - ✅ Can read existing data (documents, chats history)
     - ✅ Can view plans and pricing
     - ❌ Cannot create new chats
     - ❌ Cannot upload new documents
     - ❌ Cannot scrape new websites
     - ⚠️ Renewal banner on every page

   - **After Grace Period**:
     - ❌ Complete service block
     - ✅ Only renewal endpoints accessible
     - ✅ Can view renewal information
     - ✅ Can initiate renewal payment

3. **Renewal Process**:
   - User clicks "Renew Subscription"
   - System generates Paystack payment link
   - User completes payment manually
   - System verifies payment via webhook
   - **Publishes**: `subscription.renewed` event
   - All services receive event and update caches
   - Subscription reactivated immediately
   - Usage counters reset
   - Email confirmation sent (async)

4. **Data Retention**:
   - Keep all data (documents, vectors, chat history) for 30 days after expiry
   - After 30 days: Archive or delete (separate discussion)

---

## Event-Driven Architecture Benefits

### Why Async Messaging is Better:

1. **Resilience**:
   - If communications-service is down, emails queue up and send when it recovers
   - Billing service doesn't fail if authorization server is temporarily unavailable

2. **Performance**:
   - User gets response immediately after usage increment (don't wait for DB update)
   - Subscription renewal completes fast (notifications sent in background)

3. **Scalability**:
   - Multiple consumers can process usage events in parallel
   - Easy to add new consumers (e.g., analytics service)

4. **Loose Coupling**:
   - Services don't need to know about each other
   - Easy to add/remove features without changing other services

5. **Event Sourcing**:
   - Complete audit trail of all usage and subscription changes
   - Can replay events for debugging or analytics

### Trade-offs:

1. **Eventual Consistency**:
   - Usage counts might be slightly delayed (usually < 1 second)
   - Solution: Use synchronous check before operation, async increment after

2. **Complexity**:
   - Need to manage RabbitMQ infrastructure
   - Need to handle message failures and DLQs
   - Solution: Use existing RabbitMQ setup, implement proper monitoring

3. **Debugging**:
   - Harder to trace flow across services
   - Solution: Add correlation IDs to all events, use logging aggregation

---

## Hybrid Approach Summary

| Operation | Method | Reason |
|-----------|--------|--------|
| Check usage limit | REST API (Sync) | Real-time decision needed before operation |
| Increment usage | RabbitMQ (Async) | Fire-and-forget, don't block user |
| Check feature access | REST API (Sync) + Redis cache | Real-time decision, cached for performance |
| Subscription expiry | RabbitMQ (Async) | Background job, notify all services |
| Subscription renewal | REST API (Sync) + RabbitMQ (Async) | User needs payment URL (sync), notifications are async |
| Send notifications | RabbitMQ (Async) | Background job, don't block user |
| Update tenant status | RabbitMQ (Async) | Event-driven, multiple services need to know |

---

## Testing Strategy

1. **Unit Tests**: Each service method
2. **Integration Tests**: API endpoints with real database
3. **Message Tests**: RabbitMQ message publishing and consumption
4. **E2E Tests**: Full user flows (upload → limit → renewal)
5. **Load Tests**: Usage tracking under concurrent requests
6. **Chaos Tests**: Service failures (RabbitMQ down, billing-service down)
7. **Manual Tests**: Paystack payment integration

---

## Deployment Considerations

1. **Database Migrations**: Alembic migrations for any new fields
2. **RabbitMQ Setup**:
   - Create exchanges and queues
   - Configure DLQs
   - Set up monitoring (e.g., RabbitMQ Management UI)
3. **Scheduler Deployment**: Run scheduler as separate process or background task
4. **Redis Setup**: For caching subscription status and feature flags
5. **Environment Variables**: Add scheduler config, grace period duration, RabbitMQ URLs
6. **Monitoring**:
   - Track expired subscriptions
   - Monitor DLQs for failed events
   - Alert on usage limit hits
   - Track renewal conversion rates

---

## Estimated Implementation Time

- Phase 1 (Usage API + RabbitMQ consumer): 6-8 hours
- Phase 2 (Chat enforcement + RabbitMQ publisher): 3-4 hours
- Phase 3 (Onboarding enforcement + RabbitMQ publisher): 4-5 hours
- Phase 4 (Expiry handling + RabbitMQ events): 8-10 hours
- Phase 5 (Renewal flow): 4-6 hours
- Phase 6 (Expiry enforcement with Redis cache): 4-6 hours
- Phase 7 (Feature flags): 2-3 hours
- Phase 8 (Grace period): 2-3 hours
- Phase 9 (Notifications + RabbitMQ): 6-8 hours
- RabbitMQ infrastructure setup: 3-4 hours
- Redis caching setup: 2-3 hours
- Testing and debugging: 10-12 hours

**Total**: 54-72 hours (7-9 working days)

---

## Priority Order (if phased rollout):
1. **Phase 1** - Usage API + RabbitMQ infrastructure (required for everything else)
2. **Phase 4** - Expiry handling + events (most critical business need)
3. **Phase 5** - Renewal flow (enables revenue)
4. **Phase 2** - Chat enforcement (highest usage)
5. **Phase 3** - Onboarding enforcement
6. **Phase 6** - Expiry enforcement with caching
7. **Phase 8** - Grace period (improves UX)
8. **Phase 9** - Notifications
9. **Phase 7** - Feature flags (when features exist)

---

## Next Steps

1. Review this plan with team
2. Decide on implementation priorities
3. Set up RabbitMQ exchanges and queues
4. Set up Redis for caching
5. Create detailed task breakdown for Phase 1
6. Begin implementation

---

## Open Questions for Discussion

1. **Grace period duration**: 3 days is recommended, should we make it configurable?
2. **Data retention policy**: How long to keep data after expiry? 30 days? 60 days?
3. **Notification frequency**: Are the notification timings (7/3/1 days) appropriate?
4. **Failed payment retries**: Should we auto-retry failed renewal payments?
5. **Usage overage**: What happens if user exceeds limits during grace period?
6. **Multi-currency**: Should we support multiple currencies beyond NGN?
7. **Refunds**: How to handle refunds for partial subscription periods?
8. **Admin override**: Should admins be able to manually extend grace periods?