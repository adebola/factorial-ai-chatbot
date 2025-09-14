package io.factorialsystems.authorizationserver2.model;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import lombok.ToString;

import java.time.OffsetDateTime;
import java.util.Map;
import java.util.UUID;

/**
 * Tenant-specific settings for chat widget and branding customization
 */
@Getter
@Setter
@ToString
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class TenantSettings {
    
    private String id;
    private String tenantId;
    
    // Company branding colors
    private String primaryColor;    // Hex color code #RRGGBB
    private String secondaryColor;  // Hex color code #RRGGBB
    
    // Chat widget text customization
    private String hoverText;
    private String welcomeMessage;
    private String chatWindowTitle;
    
    // Company logo settings
    @Builder.Default
    private String companyLogoUrl = null;  // Public URL for the uploaded logo (null by default)
    
    // Future extensibility
    private Map<String, Object> additionalSettings;
    
    // Status
    private Boolean isActive;
    
    // Timestamps
    private OffsetDateTime createdAt;
    private OffsetDateTime updatedAt;
    
    /**
     * Generate a new UUID for the settings
     */
    public void generateId() {
        if (this.id == null) {
            this.id = UUID.randomUUID().toString();
        }
    }
    
    /**
     * Set default values for new tenant settings
     */
    public void setDefaults() {
        if (this.primaryColor == null) {
            this.primaryColor = "#5D3EC1";  // Default factorial purple
        }
        if (this.secondaryColor == null) {
            this.secondaryColor = "#C15D3E";  // Default factorial orange
        }
        if (this.hoverText == null) {
            this.hoverText = "Chat with us!";
        }
        if (this.welcomeMessage == null) {
            this.welcomeMessage = "Hello! How can I help you today?";
        }
        if (this.chatWindowTitle == null) {
            this.chatWindowTitle = "Chat Support";
        }
        if (this.isActive == null) {
            this.isActive = true;
        }
        if (this.additionalSettings == null) {
            this.additionalSettings = Map.of();
        }
    }
    
    /**
     * Generate chat icon initials from company name
     * @param companyName The company name to generate initials from
     * @return 1-2 character initials for display
     */
    public static String generateChatIconInitials(String companyName) {
        if (companyName == null || companyName.trim().isEmpty()) {
            return "CB"; // ChatBot fallback
        }
        
        String[] words = companyName.trim().split("\\s+");
        StringBuilder initials = new StringBuilder();
        
        // Take first letter of first word (always)
        initials.append(words[0].charAt(0));
        
        // If there are multiple words, take first letter of second word
        if (words.length > 1 && words[1].length() > 0) {
            initials.append(words[1].charAt(0));
        }
        // If single word and long enough, take second character
        else if (words.length == 1 && words[0].length() > 1) {
            initials.append(words[0].charAt(1));
        }
        
        return initials.toString().toUpperCase();
    }
    
    /**
     * Get the display logo - either URL or generated initials
     * @param companyName The company name for fallback initials
     * @return Object containing logo info for frontend
     */
    public ChatLogoInfo getChatLogoInfo(String companyName) {
        if (this.companyLogoUrl != null && !this.companyLogoUrl.trim().isEmpty()) {
            return new ChatLogoInfo("url", this.companyLogoUrl, null);
        } else {
            String initials = generateChatIconInitials(companyName);
            return new ChatLogoInfo("initials", null, initials);
        }
    }
    
    /**
     * Validate hex color format
     */
    public static boolean isValidHexColor(String color) {
        return color != null && color.matches("^#[0-9A-Fa-f]{6}$");
    }
    
    /**
     * Helper class for chat logo information
     */
    @Getter
    @Setter
    @ToString
    @NoArgsConstructor
    @AllArgsConstructor
    public static class ChatLogoInfo {
        private String type;      // "url" or "initials"
        private String url;       // Logo URL if available
        private String initials;  // Generated initials if no logo
    }
}