package io.factorialsystems.authorizationserver.model;

import com.fasterxml.jackson.annotation.JsonIgnore;
import lombok.*;
import java.time.LocalDateTime;
import java.util.List;

/**
 * Tenant entity representing organizations/companies in the multi-tenant OAuth2 system.
 * Each tenant has their own OAuth2 client configuration and isolated user management.
 */
@Getter
@Setter
@ToString
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class Tenant {
    
    /**
     * Unique tenant identifier (UUID)
     */
    private String id;
    
    /**
     * Organization/company name
     */
    private String name;
    
    /**
     * Unique domain identifier (e.g., 'acme-corp', 'factorial-systems')
     */
    private String domain;
    
    /**
     * OAuth2 client identifier for this tenant
     * Format: tenant_{tenant_id}_web
     */
    private String clientId;
    
    /**
     * OAuth2 client secret (encrypted/hashed)
     */
    @JsonIgnore
    private String clientSecret;
    
    /**
     * Array of allowed OAuth2 redirect URIs for this tenant
     */
    private List<String> callbackUrls;
    
    /**
     * Array of allowed OAuth2 scopes for this tenant
     * Default: ['openid', 'profile', 'documents:read', 'chat:access']
     */
    private List<String> allowedScopes;
    
    /**
     * Whether the tenant is active and can authenticate
     */
    private Boolean isActive;
    
    /**
     * Reference to subscription plan (for future billing integration)
     */
    private String planId;
    
    /**
     * Legacy API key for WebSocket connections (to be deprecated)
     */
    @JsonIgnore
    private String apiKey;
    
    // Audit fields
    /**
     * When the tenant was created
     */
    private LocalDateTime createdAt;
    
    /**
     * When the tenant was last updated
     */
    private LocalDateTime updatedAt;
    
    /**
     * User ID who created this tenant (nullable for system-created tenants)
     */
    private String createdBy;
    
    // Helper methods for OAuth2 integration
    
    /**
     * Check if a redirect URI is allowed for this tenant
     */
    public boolean isCallbackUrlAllowed(String redirectUri) {
        return callbackUrls != null && callbackUrls.contains(redirectUri);
    }
    
    /**
     * Check if a scope is allowed for this tenant
     */
    public boolean isScopeAllowed(String scope) {
        return allowedScopes != null && allowedScopes.contains(scope);
    }
    
    /**
     * Generate the standard OAuth2 client ID for this tenant
     */
    public String generateClientId() {
        return String.format("tenant_%s_web", this.id);
    }
    
    /**
     * Check if tenant is ready for OAuth2 operations
     */
    public boolean isOAuth2Ready() {
        return isActive != null && isActive && 
               clientId != null && !clientId.trim().isEmpty() &&
               clientSecret != null && !clientSecret.trim().isEmpty() &&
               callbackUrls != null && !callbackUrls.isEmpty();
    }
}