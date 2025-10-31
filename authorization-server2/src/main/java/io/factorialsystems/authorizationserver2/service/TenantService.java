package io.factorialsystems.authorizationserver2.service;

import io.factorialsystems.authorizationserver2.mapper.TenantMapper;
import io.factorialsystems.authorizationserver2.model.Tenant;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.security.SecureRandom;
import java.time.OffsetDateTime;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class TenantService {
    private final RabbitTemplate rabbitTemplate;
    private final TenantMapper tenantMapper;
    private final RedisCacheService cacheService;
    private final BillingServiceClient billingServiceClient;
    private final TenantSettingsService tenantSettingsService;
    private final UserCreationPublisher userCreationPublisher;
    private static final SecureRandom secureRandom = new SecureRandom();
    private static final String ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";

    @Value("${authorization.config.rabbitmq.key.widget}")
    private String widgetRoutingKey;

    @Value("${authorization.config.rabbitmq.exchange.name}")
    private String exchange;
    
    public Tenant findById(String id) {
        // Check cache first
        Tenant cachedTenant = cacheService.getCachedTenant(id);
        if (cachedTenant != null) {
            return cachedTenant;
        }
        
        // Fetch from database and cache
        Tenant tenant = tenantMapper.findById(id);
        if (tenant != null) {
            cacheService.cacheTenant(tenant);
        }
        return tenant;
    }

    public Tenant findByDomain(String domain) {
        // Fetch from database and cache
        Tenant tenant = tenantMapper.findByDomain(domain);
        if (tenant != null) {
            cacheService.cacheTenant(tenant);
        }
        return tenant;
    }
    
    public Tenant findByName(String name) {
        return tenantMapper.findByName(name);
    }
    
    public Tenant findByApiKey(String apiKey) {
        // Check cache first
        Tenant cachedTenant = cacheService.getCachedTenantByApiKey(apiKey);
        if (cachedTenant != null) {
            return cachedTenant;
        }
        
        // Fetch from database and cache
        Tenant tenant = tenantMapper.findByApiKey(apiKey);
        if (tenant != null) {
            cacheService.cacheTenant(tenant);
        }
        return tenant;
    }
    
    /**
     * Generate a secure API key for the tenant using the same algorithm as the onboarding service
     * Generates a 64-character string using letters and digits
     */
    public String generateApiKey() {
        StringBuilder apiKey = new StringBuilder(64);
        for (int i = 0; i < 64; i++) {
            apiKey.append(ALPHABET.charAt(secureRandom.nextInt(ALPHABET.length())));
        }
        return apiKey.toString();
    }

    @Transactional
    public Tenant createTenant(String name, String domain, String description) {
        // Check if tenant already exists
        if (findByDomain(domain) != null) {
            throw new IllegalArgumentException("A tenant with this domain already exists");
        }

        if (findByName(name) != null) {
            throw new IllegalArgumentException("A tenant with this name already exists");
        }
        
        // Generate unique API key
        String apiKey = generateApiKey();
        while (tenantMapper.findByApiKey(apiKey) != null) {
            apiKey = generateApiKey();
        }
        
        // Get free-tier plan ID from billing service
        String freePlanId = null;
        try {
            freePlanId = billingServiceClient.getFreeTierPlanId();
            log.info("Retrieved free-tier plan ID from billing service: {} for new tenant", freePlanId);
        } catch (Exception e) {
            log.warn("Failed to retrieve free-tier plan ID from billing service, tenant will be created without plan: {}", e.getMessage());
            // Continue creating tenant without plan - plan can be assigned later
        }
        
        // Create new tenant
        Tenant tenant = Tenant.builder()
                .id(UUID.randomUUID().toString())
                .name(name.trim())
                .domain(domain.toLowerCase().trim())
                .apiKey(apiKey)
                .planId(freePlanId)
                .isActive(true)
                .createdAt(OffsetDateTime.now())
                .updatedAt(OffsetDateTime.now())
                .build();
        
        int result = tenantMapper.insert(tenant);
        if (result <= 0) {
            throw new RuntimeException("Failed to create tenant");
        }

        rabbitTemplate.convertAndSend(exchange, widgetRoutingKey, tenant.getId());
        
        log.info("Created new tenant: id={}, name={}, domain={}, apiKey={}", 
                tenant.getId(), tenant.getName(), tenant.getDomain(), 
                apiKey.substring(0, 8) + "..." // Log only first 8 characters for security
        );
        
        // Cache the newly created tenant
        cacheService.cacheTenant(tenant);
        
        // Create default tenant settings
        try {
            tenantSettingsService.createDefaultSettings(tenant.getId());
            log.info("Created default settings for tenant: {}", tenant.getId());
        } catch (Exception e) {
            log.error("Failed to create default settings for tenant: {} - {}", tenant.getId(), e.getMessage());
            throw new RuntimeException("Failed to create default tenant settings: " + e.getMessage(), e);
        }

        // Publish user creation event to billing service for automatic subscription creation
        try {
            boolean published = userCreationPublisher.publishUserCreated(tenant.getId(), tenant.getCreatedAt());
            if (!published) {
                log.warn("Failed to publish user.created event for tenant {} - subscription may need to be created manually", tenant.getId());
            }
        } catch (Exception e) {
            log.error("Error publishing user.created event for tenant {}: {}", tenant.getId(), e.getMessage());
            // Don't fail tenant creation if event publishing fails
        }

        return tenant;
    }
    
    @Transactional
    public Tenant updateTenant(Tenant tenant) {
        tenant.setUpdatedAt(OffsetDateTime.now());
        int result = tenantMapper.update(tenant);
        if (result <= 0) {
            throw new RuntimeException("Failed to update tenant");
        }
        
        log.info("Updated tenant: id={}, name={}, domain={}", tenant.getId(), tenant.getName(), tenant.getDomain());
        
        // Update cache with new tenant data
        cacheService.evictTenant(tenant.getId());
        cacheService.cacheTenant(tenant);
        
        return tenant;
    }
    
    public boolean isDomainAvailable(String domain) {
        return findByDomain(domain.toLowerCase().trim()) == null;
    }
    
    public boolean isNameAvailable(String name) {
        return findByName(name.trim()) == null;
    }
    
    @Transactional
    public boolean updateTenantPlan(String tenantId, String planId) {
        try {
            // Validate tenant exists
            Tenant existingTenant = findById(tenantId);
            if (existingTenant == null) {
                log.warn("Cannot update plan for non-existent tenant: {}", tenantId);
                return false;
            }

            // Update plan_id in database
            int rowsUpdated = tenantMapper.updatePlanId(tenantId, planId);

            if (rowsUpdated > 0) {
                // Clear cache to ensure fresh data on next access
                cacheService.evictTenant(tenantId);

                log.info("Successfully updated tenant {} plan from {} to {}",
                        tenantId, existingTenant.getPlanId(), planId);
                return true;
            } else {
                log.warn("Failed to update tenant {} plan - no rows affected", tenantId);
                return false;
            }

        } catch (Exception e) {
            log.error("Error updating tenant {} plan to {}: {}", tenantId, planId, e.getMessage(), e);
            return false;
        }
    }

    @Transactional
    public boolean updateTenantSubscription(String tenantId, String subscriptionId, String planId) {
        try {
            // Validate tenant exists
            Tenant existingTenant = findById(tenantId);
            if (existingTenant == null) {
                log.warn("Cannot update subscription for non-existent tenant: {}", tenantId);
                return false;
            }

            // Update subscription_id and plan_id in database
            int rowsUpdated = tenantMapper.updateSubscriptionAndPlan(tenantId, subscriptionId, planId);

            if (rowsUpdated > 0) {
                // Clear cache to ensure fresh data on next access
                cacheService.evictTenant(tenantId);

                log.info("Successfully updated tenant {} subscription to {} and plan to {}",
                        tenantId, subscriptionId, planId);
                return true;
            } else {
                log.warn("Failed to update tenant {} subscription and plan - no rows affected", tenantId);
                return false;
            }

        } catch (Exception e) {
            log.error("Error updating tenant {} subscription to {} and plan to {}: {}",
                    tenantId, subscriptionId, planId, e.getMessage(), e);
            return false;
        }
    }
}