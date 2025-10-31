# Plan & Subscription Management Implementation Guide

## Overview
This document provides a step-by-step guide to implement comprehensive plan/subscription management across billing-service and authorization-server2.

## Implementation Status

### ✅ Already Implemented
1. Free-tier creation (14-day trial from registration date)
2. Basic plan switching with proration
3. RabbitMQ integration (billing → auth-server)
4. Tenant model has `planId` and `subscriptionId` fields

### 🚧 To Be Implemented
1. Same-plan validation
2. Downgrade handling (end-of-period scheduling)
3. Auto-create subscription on user registration
4. RabbitMQ consumer in auth-server
5. RabbitMQ publisher for user events (auth-server → billing)

---

## Phase 1: Billing Service Enhancements

### 1.1 Add Same-Plan Validation

**File**: `billing-service/app/api/plans.py`

**Location**: In `switch_tenant_plan()` function, after line 786 (Get current plan for comparison)

```python
# Get current plan for comparison
current_plan = plan_service.get_plan_by_id(existing_subscription.plan_id)

# ADD THIS VALIDATION:
# Check if user is trying to switch to the same plan
if existing_subscription.plan_id == new_plan.id:
    # Check if subscription is still valid (not expired)
    from ..models.subscription import SubscriptionStatus
    if existing_subscription.status in [
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.TRIALING
    ]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"You are already subscribed to the {new_plan.name} plan"
        )
```

### 1.2 Add Pending Plan Fields to Subscription Model

**File**: `billing-service/app/models/subscription.py`

Find the `Subscription` class and add these fields:

```python
# Add after existing fields (around line 80-100)
pending_plan_id = Column(String(36), nullable=True)
pending_billing_cycle = Column(Enum(BillingCycle), nullable=True)
pending_plan_effective_date = Column(DateTime(timezone=True), nullable=True)
```

### 1.3 Create Alembic Migration

**Command**:
```bash
cd billing-service
alembic revision -m "add pending plan fields to subscriptions"
```

**File**: `billing-service/alembic/versions/xxx_add_pending_plan_fields.py`

```python
"""add pending plan fields to subscriptions

Revision ID: xxx
Revises: yyy
Create Date: 2025-xx-xx

"""
from alembic import op
import sqlalchemy as sa

revision = 'xxx'
down_revision = 'yyy'  # Update with actual previous revision
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('subscriptions',
        sa.Column('pending_plan_id', sa.String(36), nullable=True))
    op.add_column('subscriptions',
        sa.Column('pending_billing_cycle', sa.String(20), nullable=True))
    op.add_column('subscriptions',
        sa.Column('pending_plan_effective_date', sa.DateTime(timezone=True), nullable=True))

def downgrade():
    op.drop_column('subscriptions', 'pending_plan_effective_date')
    op.drop_column('subscriptions', 'pending_billing_cycle')
    op.drop_column('subscriptions', 'pending_plan_id')
```

**Run**:
```bash
alembic upgrade head
```

### 1.4 Add Downgrade Logic to Subscription Service

**File**: `billing-service/app/services/subscription_service.py`

**Location**: In `switch_subscription_plan()` method, after calculating new_amount (around line 295)

```python
# Calculate new amount
if billing_cycle == BillingCycle.YEARLY:
    new_amount = new_plan.yearly_plan_cost
    old_amount = current_plan.yearly_plan_cost if current_plan else Decimal(0)
else:
    new_amount = new_plan.monthly_plan_cost
    old_amount = current_plan.monthly_plan_cost if current_plan else Decimal(0)

# ADD THIS DOWNGRADE LOGIC:
# Check if this is a downgrade (new plan costs less)
is_downgrade = new_amount < old_amount

if is_downgrade and subscription.status == SubscriptionStatus.ACTIVE:
    # Schedule downgrade for end of current period
    subscription.pending_plan_id = new_plan_id
    subscription.pending_billing_cycle = billing_cycle
    subscription.pending_plan_effective_date = subscription.current_period_end

    # Log the scheduled change
    self._log_subscription_change(
        subscription=subscription,
        change_type="plan_downgrade_scheduled",
        previous_plan_id=old_plan_id,
        new_plan_id=new_plan_id,
        previous_amount=old_amount,
        new_amount=new_amount,
        reason="User initiated plan downgrade - scheduled for end of period"
    )

    self.db.commit()

    return {
        "success": True,
        "subscription_id": subscription.id,
        "old_plan_id": old_plan_id,
        "new_plan_id": new_plan_id,
        "old_amount": float(old_amount),
        "new_amount": float(new_amount),
        "prorated_amount": None,
        "effective_immediately": False,
        "scheduled_for": subscription.current_period_end.isoformat(),
        "message": f"Downgrade to {new_plan.name} scheduled for {subscription.current_period_end.date()}"
    }
```

### 1.5 Update API Response for Downgrades

**File**: `billing-service/app/api/plans.py`

**Location**: In `switch_tenant_plan()`, update the response handling (around line 831)

```python
# Replace the existing return block with this enhanced version:
response_data = {
    "message": f"Successfully switched to {new_plan.name} plan" if switch_result.get("effective_immediately") else f"Downgrade to {new_plan.name} scheduled",
    "plan_switch": {
        "tenant_id": tenant_id,
        "subscription_id": existing_subscription.id,
        "action": "plan_switched" if switch_result.get("effective_immediately") else "plan_downgrade_scheduled",
        "previous_plan": {
            "id": current_plan.id if current_plan else None,
            "name": current_plan.name if current_plan else "Unknown"
        },
        "new_plan": {
            "id": new_plan.id,
            "name": new_plan.name,
            "description": new_plan.description,
            "document_limit": new_plan.document_limit,
            "website_limit": new_plan.website_limit,
            "daily_chat_limit": new_plan.daily_chat_limit,
            "monthly_chat_limit": new_plan.monthly_chat_limit,
            "features": new_plan.features
        }
    },
    "billing_info": {
        "billing_cycle": plan_switch.billing_cycle,
        "old_cost": float(switch_result["old_amount"]),
        "new_cost": float(switch_result["new_amount"]),
        "prorated_amount": switch_result.get("prorated_amount"),
        "is_upgrade": float(switch_result["new_amount"]) > float(switch_result["old_amount"]),
        "is_downgrade": float(switch_result["new_amount"]) < float(switch_result["old_amount"])
    },
    "effective_immediately": switch_result.get("effective_immediately", True),
    "rabbitmq_notified": rabbitmq_success
}

# Add scheduled date if it's a downgrade
if not switch_result.get("effective_immediately"):
    response_data["scheduled_effective_date"] = switch_result.get("scheduled_for")

return response_data
```

---

## Phase 2: RabbitMQ Consumer for User Events (Billing Service)

### 2.1 Create User Consumer

**File**: `billing-service/app/messaging/__init__.py`

```python
# Empty file to make it a package
```

**File**: `billing-service/app/messaging/user_consumer.py`

```python
"""RabbitMQ consumer for user creation events from authorization server"""
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any

from ..core.database import SessionLocal
from ..services.subscription_service import SubscriptionService
from ..services.plan_service import PlanService
from ..services.rabbitmq_service import rabbitmq_service
from ..models.subscription import BillingCycle

logger = logging.getLogger(__name__)


class UserEventConsumer:
    """Consumer for handling user-related events from authorization server"""

    def __init__(self):
        self.db = None

    def handle_user_created(self, message: Dict[str, Any]):
        """
        Handle user_created event from auth-server

        Creates a Basic plan subscription with 14-day trial from registration date
        """
        tenant_id = message.get("tenant_id")
        user_id = message.get("user_id")
        created_at_str = message.get("created_at")

        if not tenant_id or not created_at_str:
            logger.error(f"Invalid user_created message: missing tenant_id or created_at")
            return

        logger.info(f"Processing user_created event for tenant: {tenant_id}")

        # Create fresh database session
        self.db = SessionLocal()

        try:
            # Parse registration date
            from dateutil import parser
            registration_date = parser.isoparse(created_at_str.replace('Z', '+00:00'))

            # Get Basic plan
            plan_service = PlanService(self.db)
            basic_plan = plan_service.get_plan_by_name("Basic")

            if not basic_plan or not basic_plan.is_active:
                logger.error("Basic plan not found or inactive - cannot create subscription")
                return

            # Calculate 14-day trial end from registration date
            trial_end = registration_date + timedelta(days=14)

            # Check if subscription already exists (idempotency)
            subscription_service = SubscriptionService(self.db)
            existing = subscription_service.get_subscription_by_tenant(tenant_id)

            if existing:
                logger.info(f"Subscription already exists for tenant {tenant_id} - skipping creation")
                return

            # Create subscription with custom trial end
            subscription = subscription_service.create_subscription(
                tenant_id=tenant_id,
                plan_id=basic_plan.id,
                billing_cycle=BillingCycle.MONTHLY,
                start_trial=False,
                custom_trial_end=trial_end,
                metadata={
                    "auto_created": True,
                    "trigger": "user_registration",
                    "user_id": user_id,
                    "registration_date": created_at_str
                }
            )

            logger.info(
                f"✅ Created subscription {subscription.id} for tenant {tenant_id} "
                f"with {basic_plan.name} plan (trial until {trial_end.date()})"
            )

            # Notify auth-server back via RabbitMQ
            rabbitmq_success = rabbitmq_service.publish_plan_update(
                tenant_id=tenant_id,
                subscription_id=subscription.id,
                plan_id=basic_plan.id,
                action="subscription_created"
            )

            if not rabbitmq_success:
                logger.warning(
                    f"Failed to publish subscription_created to RabbitMQ for tenant {tenant_id}"
                )

        except Exception as e:
            logger.error(f"Error handling user_created event: {e}", exc_info=True)
            if self.db:
                self.db.rollback()
        finally:
            if self.db:
                self.db.close()


def start_user_event_consumer():
    """Start the RabbitMQ consumer for user events"""
    import pika
    import os

    host = os.environ.get("RABBITMQ_HOST", "localhost")
    port = int(os.environ.get("RABBITMQ_PORT", "5672"))
    username = os.environ.get("RABBITMQ_USERNAME", "guest")
    password = os.environ.get("RABBITMQ_PASSWORD", "guest")
    exchange = os.environ.get("RABBITMQ_EXCHANGE", "topic-exchange")
    queue_name = "billing.user.events"
    routing_key = "user.created"

    try:
        # Setup connection
        credentials = pika.PlainCredentials(username, password)
        parameters = pika.ConnectionParameters(
            host=host,
            port=port,
            credentials=credentials,
            heartbeat=600,
            blocked_connection_timeout=300
        )

        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()

        # Declare exchange
        channel.exchange_declare(
            exchange=exchange,
            exchange_type='topic',
            durable=True
        )

        # Declare queue
        channel.queue_declare(queue=queue_name, durable=True)

        # Bind queue to exchange
        channel.queue_bind(
            exchange=exchange,
            queue=queue_name,
            routing_key=routing_key
        )

        logger.info(f"✅ User event consumer started - listening on {queue_name}")

        consumer = UserEventConsumer()

        def callback(ch, method, properties, body):
            """Process incoming messages"""
            try:
                message = json.loads(body)
                logger.debug(f"Received message: {message}")

                action = message.get("action")
                if action == "user_created":
                    consumer.handle_user_created(message)
                else:
                    logger.warning(f"Unknown action: {action}")

                # Acknowledge message
                ch.basic_ack(delivery_tag=method.delivery_tag)

            except Exception as e:
                logger.error(f"Error processing message: {e}", exc_info=True)
                # Reject and requeue message
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

        # Start consuming
        channel.basic_consume(
            queue=queue_name,
            on_message_callback=callback
        )

        logger.info("Waiting for user events...")
        channel.start_consuming()

    except KeyboardInterrupt:
        logger.info("Consumer stopped by user")
    except Exception as e:
        logger.error(f"Fatal error in consumer: {e}", exc_info=True)


if __name__ == "__main__":
    # Allow running consumer standalone
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    start_user_event_consumer()
```

### 2.2 Add Consumer Startup Script

**File**: `billing-service/start_consumer.py`

```python
"""Script to start the RabbitMQ consumer for user events"""
import logging
from app.messaging.user_consumer import start_user_event_consumer

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    logger = logging.getLogger(__name__)
    logger.info("Starting billing service RabbitMQ consumer...")

    start_user_event_consumer()
```

**Usage**:
```bash
cd billing-service
python start_consumer.py
```

### 2.3 Add to requirements.txt

**File**: `billing-service/requirements.txt`

Ensure these are present:
```
pika>=1.3.0
python-dateutil>=2.8.2
```

---

## Phase 3: Authorization Server Enhancements

### 3.1 Create Billing Service Client (Publisher)

**File**: `authorization-server2/src/main/java/io/factorialsystems/authorizationserver2/messaging/BillingServiceClient.java`

```java
package io.factorialsystems.authorizationserver2.messaging;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.factorialsystems.authorizationserver2.dto.UserCreatedMessage;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.time.OffsetDateTime;

@Slf4j
@Service
@RequiredArgsConstructor
public class BillingServiceClient {

    private final RabbitTemplate rabbitTemplate;
    private final ObjectMapper objectMapper;

    @Value("${rabbitmq.exchange:topic-exchange}")
    private String exchange;

    @Value("${rabbitmq.user-created-routing-key:user.created}")
    private String userCreatedRoutingKey;

    /**
     * Publish user_created event to billing service
     */
    public boolean publishUserCreated(String tenantId, String userId, OffsetDateTime createdAt) {
        try {
            UserCreatedMessage message = UserCreatedMessage.builder()
                    .tenantId(tenantId)
                    .userId(userId)
                    .createdAt(createdAt.toString())
                    .action("user_created")
                    .timestamp(OffsetDateTime.now().toString())
                    .build();

            rabbitTemplate.convertAndSend(exchange, userCreatedRoutingKey, message);

            log.info("Published user_created event for tenant: {}, user: {}", tenantId, userId);
            return true;

        } catch (Exception e) {
            log.error("Failed to publish user_created event for tenant: {}", tenantId, e);
            return false;
        }
    }
}
```

### 3.2 Create User Created Message DTO

**File**: `authorization-server2/src/main/java/io/factorialsystems/authorizationserver2/dto/UserCreatedMessage.java`

```java
package io.factorialsystems.authorizationserver2.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class UserCreatedMessage {
    private String tenantId;
    private String userId;
    private String createdAt;
    private String action;
    private String timestamp;
}
```

### 3.3 Create Plan Update Consumer

**File**: `authorization-server2/src/main/java/io/factorialsystems/authorizationserver2/messaging/PlanUpdateConsumer.java`

```java
package io.factorialsystems.authorizationserver2.messaging;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.factorialsystems.authorizationserver2.dto.PlanUpdateMessage;
import io.factorialsystems.authorizationserver2.service.TenantService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Slf4j
@Component
@RequiredArgsConstructor
public class PlanUpdateConsumer {

    private final TenantService tenantService;
    private final ObjectMapper objectMapper;

    @RabbitListener(queues = "${rabbitmq.plan-update-queue:auth.plan.updates}")
    public void handlePlanUpdate(PlanUpdateMessage message) {
        try {
            log.info("Received plan update: tenant={}, plan={}, subscription={}, action={}",
                    message.getTenantId(), message.getPlanId(),
                    message.getSubscriptionId(), message.getAction());

            // Update tenant with new plan and subscription IDs
            tenantService.updateTenantPlan(
                    message.getTenantId(),
                    message.getPlanId(),
                    message.getSubscriptionId()
            );

            log.info("✅ Updated tenant {} with plan {} and subscription {}",
                    message.getTenantId(), message.getPlanId(), message.getSubscriptionId());

        } catch (Exception e) {
            log.error("Error handling plan update for tenant: {}",
                    message.getTenantId(), e);
            throw e; // Reject and requeue
        }
    }
}
```

### 3.4 Create Plan Update Message DTO

**File**: `authorization-server2/src/main/java/io/factorialsystems/authorizationserver2/dto/PlanUpdateMessage.java`

```java
package io.factorialsystems.authorizationserver2.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class PlanUpdateMessage {
    private String tenantId;
    private String subscriptionId;
    private String planId;
    private String action;
    private String timestamp;
    private String oldPlanId; // Optional, for plan switches
}
```

### 3.5 Update TenantService

**File**: `authorization-server2/src/main/java/io/factorialsystems/authorizationserver2/service/TenantService.java`

Add these methods:

```java
// Add this method to TenantService

@Autowired
private BillingServiceClient billingServiceClient;

/**
 * Update tenant's plan and subscription IDs
 */
public void updateTenantPlan(String tenantId, String planId, String subscriptionId) {
    String sql = """
        UPDATE tenants
        SET plan_id = :planId,
            subscription_id = :subscriptionId,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = :tenantId
        """;

    MapSqlParameterSource params = new MapSqlParameterSource()
            .addValue("tenantId", tenantId)
            .addValue("planId", planId)
            .addValue("subscriptionId", subscriptionId);

    int updated = jdbcTemplate.update(sql, params);

    if (updated == 0) {
        throw new RuntimeException("Tenant not found: " + tenantId);
    }

    log.info("Updated tenant {} - plan: {}, subscription: {}",
            tenantId, planId, subscriptionId);
}
```

**In the tenant creation method (registerTenant or similar), add**:

```java
// After successfully creating tenant and user
Tenant createdTenant = // ... your existing code

// Publish user_created event to billing service
billingServiceClient.publishUserCreated(
        createdTenant.getId(),
        createdUser.getId(),
        createdUser.getCreatedAt()
);
```

### 3.6 Update application.yml

**File**: `authorization-server2/src/main/resources/application.yml`

```yaml
spring:
  rabbitmq:
    host: ${RABBITMQ_HOST:localhost}
    port: ${RABBITMQ_PORT:5672}
    username: ${RABBITMQ_USERNAME:guest}
    password: ${RABBITMQ_PASSWORD:guest}

rabbitmq:
  exchange: topic-exchange
  user-created-routing-key: user.created
  plan-update-queue: auth.plan.updates
  plan-update-routing-key: plan.update
```

### 3.7 Create RabbitMQ Configuration

**File**: `authorization-server2/src/main/java/io/factorialsystems/authorizationserver2/config/RabbitMQConfig.java`

```java
package io.factorialsystems.authorizationserver2.config;

import org.springframework.amqp.core.*;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RabbitMQConfig {

    @Value("${rabbitmq.exchange:topic-exchange}")
    private String exchange;

    @Value("${rabbitmq.plan-update-queue:auth.plan.updates}")
    private String planUpdateQueue;

    @Value("${rabbitmq.plan-update-routing-key:plan.update}")
    private String planUpdateRoutingKey;

    @Bean
    public TopicExchange exchange() {
        return new TopicExchange(exchange, true, false);
    }

    @Bean
    public Queue planUpdateQueue() {
        return QueueBuilder.durable(planUpdateQueue).build();
    }

    @Bean
    public Binding planUpdateBinding() {
        return BindingBuilder
                .bind(planUpdateQueue())
                .to(exchange())
                .with(planUpdateRoutingKey);
    }

    @Bean
    public Jackson2JsonMessageConverter messageConverter() {
        return new Jackson2JsonMessageConverter();
    }

    @Bean
    public RabbitTemplate rabbitTemplate(ConnectionFactory connectionFactory) {
        RabbitTemplate template = new RabbitTemplate(connectionFactory);
        template.setMessageConverter(messageConverter());
        return template;
    }
}
```

### 3.8 Add Dependencies to pom.xml

**File**: `authorization-server2/pom.xml`

```xml
<!-- Add these dependencies if not present -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
```

---

## Phase 4: Testing & Deployment

### 4.1 Test Same-Plan Validation

```bash
# Request to switch to same plan should fail
curl -X POST http://localhost:8002/api/v1/plans/switch \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "new_plan_id": "CURRENT_PLAN_ID",
    "billing_cycle": "monthly"
  }'

# Expected: HTTP 400 with message "You are already subscribed to..."
```

### 4.2 Test Downgrade Scheduling

```bash
# Request downgrade to cheaper plan
curl -X POST http://localhost:8002/api/v1/plans/switch \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "new_plan_id": "CHEAPER_PLAN_ID",
    "billing_cycle": "monthly"
  }'

# Expected: Response with effective_immediately: false and scheduled_effective_date
```

### 4.3 Test Auto-Subscription Creation

1. Start RabbitMQ consumer:
```bash
cd billing-service
python start_consumer.py
```

2. Register new user in auth-server
3. Check logs: Should see "Created subscription... with Basic plan"
4. Verify in database:
```sql
SELECT * FROM subscriptions WHERE tenant_id = 'NEW_TENANT_ID';
```

### 4.4 Deployment Checklist

- [ ] Run Alembic migration for pending plan fields
- [ ] Update environment variables:
  - `RABBITMQ_HOST`
  - `RABBITMQ_PORT`
  - `RABBITMQ_USERNAME`
  - `RABBITMQ_PASSWORD`
  - `RABBITMQ_EXCHANGE`
- [ ] Start billing service consumer as separate process/container
- [ ] Restart authorization-server to enable RabbitMQ consumer
- [ ] Verify RabbitMQ queues are created:
  - `billing.user.events`
  - `auth.plan.updates`

---

## Phase 5: Background Job (Optional - For Applying Scheduled Downgrades)

### 5.1 Create Scheduled Downgrade Processor

**File**: `billing-service/app/jobs/process_pending_plan_changes.py`

```python
"""Background job to process pending plan changes (scheduled downgrades)"""
import logging
from datetime import datetime
from sqlalchemy.orm import Session

from ..core.database import SessionLocal
from ..models.subscription import Subscription, SubscriptionStatus
from ..services.subscription_service import SubscriptionService
from ..services.rabbitmq_service import rabbitmq_service

logger = logging.getLogger(__name__)


def process_pending_plan_changes():
    """
    Process subscriptions with pending plan changes
    Apply downgrades that are scheduled for today or earlier
    """
    db: Session = SessionLocal()

    try:
        now = datetime.utcnow()

        # Find subscriptions with pending changes due today or earlier
        pending_subscriptions = db.query(Subscription).filter(
            Subscription.pending_plan_id.isnot(None),
            Subscription.pending_plan_effective_date <= now,
            Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING])
        ).all()

        logger.info(f"Found {len(pending_subscriptions)} subscriptions with pending plan changes")

        for subscription in pending_subscriptions:
            try:
                old_plan_id = subscription.plan_id
                new_plan_id = subscription.pending_plan_id
                new_billing_cycle = subscription.pending_billing_cycle

                logger.info(
                    f"Applying pending plan change for subscription {subscription.id}: "
                    f"{old_plan_id} → {new_plan_id}"
                )

                # Apply the pending change
                subscription.plan_id = new_plan_id
                subscription.billing_cycle = new_billing_cycle

                # Clear pending fields
                subscription.pending_plan_id = None
                subscription.pending_billing_cycle = None
                subscription.pending_plan_effective_date = None

                db.commit()

                # Notify auth-server
                rabbitmq_service.publish_plan_switch(
                    tenant_id=subscription.tenant_id,
                    subscription_id=subscription.id,
                    old_plan_id=old_plan_id,
                    new_plan_id=new_plan_id
                )

                logger.info(f"✅ Applied pending plan change for subscription {subscription.id}")

            except Exception as e:
                logger.error(
                    f"Error applying pending plan change for subscription {subscription.id}: {e}",
                    exc_info=True
                )
                db.rollback()

    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    process_pending_plan_changes()
```

### 5.2 Setup Cron Job

**Add to crontab** (runs daily at 2 AM):
```bash
0 2 * * * cd /path/to/billing-service && python -m app.jobs.process_pending_plan_changes >> /var/log/pending_plans.log 2>&1
```

**Or use Celery Beat** (recommended for production):

**File**: `billing-service/app/celery_app.py`

```python
from celery import Celery
from celery.schedules import crontab

celery_app = Celery('billing_service')
celery_app.config_from_object('app.celeryconfig')

@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # Run daily at 2 AM
    sender.add_periodic_task(
        crontab(hour=2, minute=0),
        process_pending_plan_changes.s(),
        name='process-pending-plan-changes'
    )

@celery_app.task
def process_pending_plan_changes():
    from app.jobs.process_pending_plan_changes import process_pending_plan_changes
    return process_pending_plan_changes()
```

---

## Summary

This guide provides a complete implementation for:

1. ✅ Same-plan validation
2. ✅ Downgrade scheduling (end-of-period)
3. ✅ Auto-create subscription on user registration
4. ✅ Bidirectional RabbitMQ communication
5. ✅ Background job for applying scheduled downgrades

All components are designed to be:
- **Idempotent**: Duplicate events are handled gracefully
- **Fault-tolerant**: Failed messages are requeued
- **Auditable**: All changes are logged
- **Scalable**: Consumers can be scaled independently

**Next Steps**:
1. Implement Phase 1 (Billing Service enhancements)
2. Run database migration
3. Implement Phase 2 (RabbitMQ consumer in billing-service)
4. Implement Phase 3 (Authorization Server enhancements)
5. Test end-to-end flow
6. Deploy and monitor
