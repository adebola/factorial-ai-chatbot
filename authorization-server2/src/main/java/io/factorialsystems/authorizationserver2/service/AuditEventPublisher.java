package io.factorialsystems.authorizationserver2.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

import java.time.OffsetDateTime;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

/**
 * Publishes audit events to the audit.events RabbitMQ exchange.
 * All events follow the fat-event pattern matching the Python audit publisher.
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class AuditEventPublisher {

    private final RabbitTemplate rabbitTemplate;

    @Value("${rabbitmq.audit.exchange:audit.events}")
    private String auditExchange;

    /**
     * Publish a security-tier audit event (login, logout, role changes).
     */
    @Async
    public void publishSecurityEvent(
            String actionType,
            String tenantId,
            String actorUserId,
            String actorEmail,
            String actorType,
            String resourceType,
            String resourceId,
            Map<String, Object> beforeState,
            Map<String, Object> afterState,
            Map<String, Object> metadata
    ) {
        publish(actionType, "security", tenantId, actorUserId, actorEmail,
                actorType, resourceType, resourceId, beforeState, afterState, metadata);
    }

    /**
     * Publish a data-tier audit event (user creation, profile updates).
     */
    @Async
    public void publishDataEvent(
            String actionType,
            String tenantId,
            String actorUserId,
            String actorEmail,
            String actorType,
            String resourceType,
            String resourceId,
            Map<String, Object> afterState
    ) {
        publish(actionType, "data", tenantId, actorUserId, actorEmail,
                actorType, resourceType, resourceId, null, afterState, null);
    }

    private void publish(
            String actionType,
            String tier,
            String tenantId,
            String actorUserId,
            String actorEmail,
            String actorType,
            String resourceType,
            String resourceId,
            Map<String, Object> beforeState,
            Map<String, Object> afterState,
            Map<String, Object> eventMetadata
    ) {
        try {
            Map<String, Object> event = new HashMap<>();
            event.put("event_id", UUID.randomUUID().toString());
            event.put("tenant_id", tenantId != null ? tenantId : "unknown");
            event.put("actor_user_id", actorUserId);
            event.put("actor_email", actorEmail);
            event.put("actor_type", actorType);
            event.put("action_type", actionType);
            event.put("tier", tier);
            event.put("resource_type", resourceType);
            event.put("resource_id", resourceId);
            event.put("source_service", "authorization-server");
            event.put("before_state", beforeState);
            event.put("after_state", afterState);
            event.put("event_metadata", eventMetadata);
            event.put("occurred_at", OffsetDateTime.now().toString());

            rabbitTemplate.convertAndSend(auditExchange, actionType, event);
            log.info("Audit event published: {} for user {}", actionType, actorEmail);
        } catch (Exception e) {
            log.warn("Failed to publish audit event {} (non-critical): {}", actionType, e.getMessage());
        }
    }
}
