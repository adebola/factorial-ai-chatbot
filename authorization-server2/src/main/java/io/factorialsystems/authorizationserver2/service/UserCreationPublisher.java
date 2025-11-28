package io.factorialsystems.authorizationserver2.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.time.OffsetDateTime;
import java.util.HashMap;
import java.util.Map;

/**
 * Publisher service for sending user creation events to the billing service via RabbitMQ.
 *
 * When a new tenant/user is created, this service publishes an event to the billing
 * service which will automatically create a Basic plan subscription with a 14-day
 * trial starting from the user's registration date.
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class UserCreationPublisher {

    private final RabbitTemplate rabbitTemplate;

    @Value("${rabbitmq.exchange:billing.events}")
    private String exchange;

    @Value("${rabbitmq.routing.key.user.created:user.created}")
    private String routingKey;

    /**
     * Publish a user creation event to RabbitMQ for billing service consumption.
     *
     * The billing service will listen for this event and automatically create
     * a Basic plan subscription with a 14-day trial.
     *
     * @param tenantId    The UUID of the tenant/user
     * @param createdAt   The timestamp when the user was created
     * @return true if successfully published, false otherwise
     */
    public boolean publishUserCreated(String tenantId, OffsetDateTime createdAt) {
        try {
            // Create message payload
            Map<String, Object> message = new HashMap<>();
            message.put("tenant_id", tenantId);
            message.put("created_at", createdAt.toString());
            message.put("event_type", "user_created");
            message.put("timestamp", OffsetDateTime.now().toString());

            // Publish to RabbitMQ - pass Map directly, Jackson2JsonMessageConverter handles serialization
            rabbitTemplate.convertAndSend(exchange, routingKey, message);

            log.info("✅ Published user.created event for tenant: {} to exchange: {} with routing key: {}",
                    tenantId, exchange, routingKey);

            return true;

        } catch (Exception e) {
            log.error("❌ Failed to publish user.created event for tenant: {}", tenantId, e);
            return false;
        }
    }

    /**
     * Check if RabbitMQ connection is healthy.
     *
     * @return true if connection is healthy, false otherwise
     */
    public boolean isRabbitMQHealthy() {
        try {
            rabbitTemplate.getConnectionFactory().createConnection().isOpen();
            return true;
        } catch (Exception e) {
            log.warn("RabbitMQ health check failed: {}", e.getMessage());
            return false;
        }
    }
}
