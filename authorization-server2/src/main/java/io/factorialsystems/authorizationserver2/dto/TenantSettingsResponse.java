package io.factorialsystems.authorizationserver2.dto;

import io.factorialsystems.authorizationserver2.model.TenantSettings;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.OffsetDateTime;
import java.util.Map;

/**
 * Response DTO for tenant settings
 */
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class TenantSettingsResponse {
    
    private String id;
    private String tenantId;
    
    // Company branding colors
    private String primaryColor;
    private String secondaryColor;
    
    // Chat widget text customization
    private String hoverText;
    private String welcomeMessage;
    private String chatWindowTitle;
    
    // Company logo settings
    private String companyLogoUrl;        // Public URL for the uploaded logo
    private TenantSettings.ChatLogoInfo chatLogo;  // Chat logo information (URL or initials)
    
    // Future extensibility
    private Map<String, Object> additionalSettings;
    
    // Status
    private Boolean isActive;
    
    // Timestamps
    private OffsetDateTime createdAt;
    private OffsetDateTime updatedAt;
}