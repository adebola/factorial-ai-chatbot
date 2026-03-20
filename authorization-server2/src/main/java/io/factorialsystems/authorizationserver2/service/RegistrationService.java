package io.factorialsystems.authorizationserver2.service;

import io.factorialsystems.authorizationserver2.event.RegistrationCompletedEvent;
import io.factorialsystems.authorizationserver2.model.Tenant;
import io.factorialsystems.authorizationserver2.model.User;
import io.factorialsystems.authorizationserver2.model.VerificationToken;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Orchestrates tenant registration in a single transaction.
 * All DB writes are atomic - if any step fails, the entire registration rolls back.
 * Side effects (RabbitMQ, Redis, email) are deferred to after-commit via
 * {@link io.factorialsystems.authorizationserver2.event.RegistrationEventListener}.
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class RegistrationService {

    private final TenantService tenantService;
    private final UserService userService;
    private final TenantSettingsService tenantSettingsService;
    private final VerificationService verificationService;
    private final ApplicationEventPublisher eventPublisher;

    /**
     * Register a new tenant with admin user in a single atomic transaction.
     *
     * @return result containing the created tenant and admin user
     * @throws IllegalArgumentException if validation fails (duplicate name/domain/username/email)
     * @throws RuntimeException if any DB write fails (entire transaction rolls back)
     */
    @Transactional
    public RegistrationResult registerTenant(String name, String domain,
                                             String adminUsername, String adminEmail,
                                             String adminPassword, String adminFirstName,
                                             String adminLastName) {

        log.info("Starting atomic registration for organization: {}", name);

        // 1. Create tenant record (DB only, no side effects)
        Tenant tenant = tenantService.insertTenant(name, domain);

        // 2. Create default tenant settings (joins this transaction)
        try {
            tenantSettingsService.createDefaultSettings(tenant.getId());
            log.info("Created default settings for tenant: {}", tenant.getId());
        } catch (Exception e) {
            log.error("Failed to create default settings for tenant: {} - {}", tenant.getId(), e.getMessage());
            throw new RuntimeException("Failed to create default tenant settings: " + e.getMessage(), e);
        }

        // 3. Create admin user record (DB only, no cache or email)
        User adminUser = userService.insertUser(
                tenant.getId(), adminUsername, adminEmail,
                adminPassword, adminFirstName, adminLastName
        );

        // 4. Assign TENANT_ADMIN role (DB only)
        userService.assignRole(adminUser.getId(), "TENANT_ADMIN");

        // 5. Generate verification token (DB only, joins this transaction)
        VerificationToken verificationToken = null;
        try {
            verificationToken = verificationService.generateEmailVerificationToken(adminUser.getId(), adminUser.getEmail());
        } catch (Exception e) {
            log.warn("Failed to generate verification token for user: {} - user can request one later", adminUser.getId(), e);
        }

        // 6. Publish event - listener fires ONLY after this transaction commits
        eventPublisher.publishEvent(new RegistrationCompletedEvent(tenant, adminUser, verificationToken));

        log.info("Atomic registration completed for tenant: {} ({}), admin user: {}",
                tenant.getName(), tenant.getId(), adminUser.getUsername());

        return new RegistrationResult(tenant, adminUser);
    }

    public record RegistrationResult(Tenant tenant, User adminUser) {}
}
