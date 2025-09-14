package io.factorialsystems.authorizationserver2.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

import java.util.Map;

@Slf4j
@Component
@RequiredArgsConstructor
public class PlanUpdateListener {
    private final ObjectMapper objectMapper;
    private final TenantService tenantService;
    private final TenantSettingsService tenantSettingsService;

    @RabbitListener(queues = "${authorization.config.rabbitmq.queue.plan-update:plan-update-queue}")
    public void handlePlanUpdate(String message) {
        log.info("Received plan update message: {}", message);
        
        try {
            Map<String, String> updateData = objectMapper.readValue(
                    message,
                    new TypeReference<Map<String, String>>() {}
            );
            
            String tenantId = updateData.get("tenant_id");
            String action = updateData.get("action");
            String timestamp = updateData.get("timestamp");
            
            if (tenantId == null || action == null) {
                log.error("Invalid update message - missing tenant_id or action: {}", message);
                return;
            }
            
            log.info("Processing {} for tenant {} (timestamp: {})", action, tenantId, timestamp);
            
            // Handle different types of updates
            boolean success = false;
            
            switch (action) {
                case "subscription_created":
                case "plan_switched":
                    String planId = updateData.get("plan_id");
                    if (planId == null) {
                        log.error("Invalid plan update message - missing plan_id: {}", message);
                        return;
                    }
                    
                    log.info("Processing plan update for tenant {} to plan {} (action: {})", tenantId, planId, action);
                    success = tenantService.updateTenantPlan(tenantId, planId);
                    
                    if (success) {
                        log.info("Successfully updated tenant {} plan to {} at {}", tenantId, planId, timestamp);
                    } else {
                        log.error("Failed to update tenant {} plan to {}", tenantId, planId);
                    }
                    break;
                    
                case "logo_updated":
                    String logoUrl = updateData.get("logo_url");
                    
                    if (logoUrl == null) {
                        log.error("Invalid logo update message - missing logo_url: {}", message);
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
                    log.warn("Unknown action type '{}' in message: {}", action, message);
                    break;
            }
            
        } catch (Exception e) {
            log.error("Error processing update message: {} - Error: {}", message, e.getMessage(), e);
        }
    }
}