package io.factorialsystems.authorizationserver2.event;

import io.factorialsystems.authorizationserver2.model.Tenant;
import io.factorialsystems.authorizationserver2.model.User;
import io.factorialsystems.authorizationserver2.model.VerificationToken;
import io.factorialsystems.authorizationserver2.service.EmailNotificationService;
import io.factorialsystems.authorizationserver2.service.RedisCacheService;
import io.factorialsystems.authorizationserver2.service.UserCreationPublisher;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

/**
 * Handles all side effects AFTER the registration transaction commits.
 * If the transaction rolls back, this listener never executes.
 * Each side effect is individually wrapped in try-catch so one failure doesn't block others.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class RegistrationEventListener {

    private final RabbitTemplate rabbitTemplate;
    private final RedisCacheService cacheService;
    private final UserCreationPublisher userCreationPublisher;
    private final EmailNotificationService emailNotificationService;

    @Value("${authorization.config.rabbitmq.key.widget}")
    private String widgetRoutingKey;

    @Value("${authorization.config.rabbitmq.exchange.name}")
    private String exchange;

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onRegistrationCompleted(RegistrationCompletedEvent event) {
        Tenant tenant = event.getTenant();
        User user = event.getUser();
        VerificationToken verificationToken = event.getVerificationToken();

        log.info("Processing post-commit side effects for tenant: {} ({})", tenant.getName(), tenant.getId());

        // 1. Publish widget generation event to RabbitMQ
        try {
            rabbitTemplate.convertAndSend(exchange, widgetRoutingKey, tenant.getId());
            log.info("Published widget generation event for tenant: {}", tenant.getId());
        } catch (Exception e) {
            log.warn("Failed to publish widget generation event for tenant: {} - {}", tenant.getId(), e.getMessage());
        }

        // 2. Cache tenant in Redis
        try {
            cacheService.cacheTenant(tenant);
            log.debug("Cached tenant in Redis: {}", tenant.getId());
        } catch (Exception e) {
            log.warn("Failed to cache tenant in Redis: {} - {}", tenant.getId(), e.getMessage());
        }

        // 3. Cache user in Redis
        try {
            cacheService.cacheUser(user);
            log.debug("Cached user in Redis: {}", user.getId());
        } catch (Exception e) {
            log.warn("Failed to cache user in Redis: {} - {}", user.getId(), e.getMessage());
        }

        // 4. Publish user.created event to billing service
        try {
            String fullName = (user.getFirstName() != null ? user.getFirstName() : "")
                    + (user.getLastName() != null ? " " + user.getLastName() : "");
            boolean published = userCreationPublisher.publishUserCreated(
                    tenant.getId(), tenant.getCreatedAt(),
                    user.getEmail(), fullName.trim(), tenant.getName()
            );
            if (!published) {
                log.error("Failed to publish user.created event for tenant {} - subscription may need to be created manually", tenant.getId());
            }
        } catch (Exception e) {
            log.error("Error publishing user.created event for tenant {}: {}", tenant.getId(), e.getMessage());
        }

        // 5. Send verification email
        if (verificationToken != null) {
            try {
                emailNotificationService.sendEmailVerification(user, verificationToken.getToken());
                log.info("Sent verification email to: {}", user.getEmail());
            } catch (Exception e) {
                log.warn("Failed to send verification email to: {} - user can request a new one later", user.getEmail(), e);
            }
        } else {
            log.error("No verification token available for user: {} - user will need to request verification email manually", user.getId());
        }

        log.info("Completed post-commit side effects for tenant: {}", tenant.getId());
    }
}
