package io.factorialsystems.authorizationserver.dto;

import lombok.Builder;
import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Set;

/**
 * DTO for user response data
 */
@Getter
@Setter
@ToString
@Builder
public class UserResponse {
    
    private String id;
    private String tenantId;
    private String username;
    private String email;
    private String firstName;
    private String lastName;
    private String fullName;
    
    // Account status
    private Boolean isActive;
    private Boolean isTenantAdmin;
    private Boolean emailVerified;
    private Boolean accountLocked;
    private LocalDateTime passwordExpiresAt;
    
    // Login tracking
    private LocalDateTime lastLoginAt;
    private Integer failedLoginAttempts;
    private LocalDateTime lastFailedLoginAt;
    
    // Invitation status
    private Boolean hasPendingInvitation;
    private LocalDateTime invitationExpiresAt;
    private String invitedBy;
    
    // Audit fields
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
    
    // Role information
    private List<RoleInfo> roles;
    private Set<String> permissions;
    
    @Getter
    @Setter
    @ToString
    @Builder
    public static class RoleInfo {
        private String id;
        private String name;
        private String description;
        private Boolean isGlobal;
        private LocalDateTime assignedAt;
        private LocalDateTime expiresAt;
        private Boolean isActive;
    }
}