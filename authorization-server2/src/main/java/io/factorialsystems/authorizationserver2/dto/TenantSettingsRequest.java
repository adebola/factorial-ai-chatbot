package io.factorialsystems.authorizationserver2.dto;

import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;


import java.util.Map;

/**
 * Request DTO for updating tenant settings
 */
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class TenantSettingsRequest {
    @Pattern(regexp = "^#[0-9A-Fa-f]{6}$", message = "Primary color must be a valid hex color code (e.g., #FF5733)")
    private String primaryColor;
    
    @Pattern(regexp = "^#[0-9A-Fa-f]{6}$", message = "Secondary color must be a valid hex color code (e.g., #FF5733)")
    private String secondaryColor;
    
    @Size(max = 255, message = "Hover text must be 255 characters or less")
    private String hoverText;
    
    @Size(max = 2000, message = "Welcome message must be 2000 characters or less")
    private String welcomeMessage;
    
    @Size(max = 100, message = "Chat window title must be 100 characters or less")
    private String chatWindowTitle;
    
    private Map<String, Object> additionalSettings;
}