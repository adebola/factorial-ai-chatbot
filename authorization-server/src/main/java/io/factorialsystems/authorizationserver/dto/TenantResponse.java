package io.factorialsystems.authorizationserver.dto;

import lombok.Builder;
import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

import java.time.LocalDateTime;
import java.util.List;

/**
 * DTO for tenant response data
 */
@Getter
@Setter
@ToString
@Builder
public class TenantResponse {
    
    private String id;
    private String name;
    private String domain;
    private String clientId;
    private List<String> callbackUrls;
    private List<String> allowedScopes;
    private Boolean isActive;
    private String planId;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
    
    // OAuth2 information
    private OAuthClientInfo oauthClient;
    
    // Statistics
    private TenantStats stats;
    
    @Getter
    @Setter
    @ToString
    @Builder
    public static class OAuthClientInfo {
        private String clientId;
        private List<String> grantTypes;
        private List<String> authenticationMethods;
        private List<String> scopes;
        private List<String> redirectUris;
    }
    
    @Getter
    @Setter
    @ToString
    @Builder
    public static class TenantStats {
        private Long userCount;
        private Long activeUserCount;
        private Long adminUserCount;
        private Long roleCount;
        private LocalDateTime lastActivity;
    }
}