package io.factorialsystems.authorizationserver2.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

import java.util.Map;

@Slf4j
@Component
@RequiredArgsConstructor
public class PlanUpdateListener {
    private final TenantService tenantService;
    private final TenantSettingsService tenantSettingsService;

    @RabbitListener(queues = "${authorization.config.rabbitmq.queue.plan-update:plan-update-queue}")
    public void handlePlanUpdate(Map<String, Object> updateData) {
        log.info("Received plan update message: {}", updateData);

        try {
            String tenantId = (String) updateData.get("tenant_id");
            String action = (String) updateData.get("action");
            String timestamp = (String) updateData.get("timestamp");

            if (tenantId == null || action == null) {
                log.error("Invalid update message - missing tenant_id or action: {}", updateData);
                return;
            }

            log.info("Processing {} for tenant {} (timestamp: {})", action, tenantId, timestamp);

            // Handle different types of updates
            boolean success = false;

            switch (action) {
                case "subscription_created":
                case "plan_switched":
                    String planId = (String) updateData.get("plan_id");
                    String subscriptionId = (String) updateData.get("subscription_id");

                    if (planId == null) {
                        log.error("Invalid plan update message - missing plan_id: {}", updateData);
                        return;
                    }

                    // If subscription_id is provided, update both subscription and plan
                    if (subscriptionId != null) {
                        log.info("Processing subscription update for tenant {} - subscription: {}, plan: {} (action: {})",
                                tenantId, subscriptionId, planId, action);
                        success = tenantService.updateTenantSubscription(tenantId, subscriptionId, planId);

                        if (success) {
                            log.info("Successfully updated tenant {} subscription to {} and plan to {} at {}",
                                    tenantId, subscriptionId, planId, timestamp);
                        } else {
                            log.error("Failed to update tenant {} subscription to {} and plan to {}",
                                    tenantId, subscriptionId, planId);
                        }
                    } else {
                        // Fallback to updating only plan_id (for backwards compatibility)
                        log.info("Processing plan-only update for tenant {} to plan {} (action: {})",
                                tenantId, planId, action);
                        success = tenantService.updateTenantPlan(tenantId, planId);

                        if (success) {
                            log.info("Successfully updated tenant {} plan to {} at {}", tenantId, planId, timestamp);
                        } else {
                            log.error("Failed to update tenant {} plan to {}", tenantId, planId);
                        }
                    }
                    break;
                    
                case "logo_updated":
                    String logoUrl = (String) updateData.get("logo_url");

                    if (logoUrl == null) {
                        log.error("Invalid logo update message - missing logo_url: {}", updateData);
                        return;
                    }

                    log.info("Processing logo update for tenant {} with URL: {}", tenantId, logoUrl);
                    success = tenantSettingsService.updateTenantLogo(tenantId, logoUrl);

                    if (success) {
                        log.info("Successfully updated tenant {} logo to {} at {}", tenantId, logoUrl, timestamp);
                    } else {
                        log.error("Failed to update tenant {} logo to {}", tenantId, logoUrl);
                    }
                    break;

                default:
                    log.warn("Unknown action type '{}' in message: {}", action, updateData);
                    break;
            }

        } catch (Exception e) {
            log.error("Error processing update message: {} - Error: {}", updateData, e.getMessage(), e);
        }
    }
}