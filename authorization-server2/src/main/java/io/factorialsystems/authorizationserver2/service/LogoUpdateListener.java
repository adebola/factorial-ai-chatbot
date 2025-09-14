package io.factorialsystems.authorizationserver2.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

import java.util.Map;

@Slf4j
@Component
@RequiredArgsConstructor
public class LogoUpdateListener {
    private final TenantSettingsService tenantSettingsService;

    @RabbitListener(queues = "${authorization.config.rabbitmq.queue.logo-update:logo-update-queue}")
    public void handleLogoUpdate(Map<String, Object> updateData) {
        log.info("Received logo update message: {}", updateData);
        
        try {
            
            String tenantId = (String) updateData.get("tenant_id");
            String eventType = (String) updateData.get("event_type");
            String timestamp = (String) updateData.get("timestamp");
            Map<String, Object> data = (Map<String, Object>) updateData.get("data");
            
            if (tenantId == null || eventType == null) {
                log.error("Invalid logo update message - missing tenant_id or event_type: {}", updateData);
                return;
            }
            
            log.info("Processing logo event '{}' for tenant {} (timestamp: {})", eventType, tenantId, timestamp);
            
            boolean success = false;
            
            switch (eventType) {
                case "logo_uploaded":
                case "logo_updated":
                    if (data == null) {
                        log.error("Invalid logo upload/update message - missing data section: {}", updateData);
                        return;
                    }
                    
                    String logoUrl = (String) data.get("logo_url");
                    if (logoUrl == null || logoUrl.trim().isEmpty()) {
                        log.error("Invalid logo upload/update message - missing or empty logo_url: {}", updateData);
                        return;
                    }
                    
                    log.info("Processing logo upload for tenant {} - URL: {}", tenantId, logoUrl);
                    
                    success = tenantSettingsService.updateTenantLogo(tenantId, logoUrl);
                    
                    if (success) {
                        log.info("Successfully updated tenant {} logo at {}", tenantId, timestamp);
                    } else {
                        log.error("Failed to update tenant {} logo", tenantId);
                    }
                    break;
                    
                case "logo_deleted":
                    log.info("Processing logo deletion for tenant {}", tenantId);
                    success = tenantSettingsService.deleteTenantLogo(tenantId);
                    
                    if (success) {
                        log.info("Successfully deleted tenant {} logo at {}", tenantId, timestamp);
                    } else {
                        log.error("Failed to delete tenant {} logo", tenantId);
                    }
                    break;
                    
                default:
                    log.warn("Unknown event type '{}' in logo message: {}", eventType, updateData);
                    break;
            }
            
        } catch (Exception e) {
            log.error("Error processing logo update message: {} - Error: {}", updateData, e.getMessage(), e);
        }
    }
}