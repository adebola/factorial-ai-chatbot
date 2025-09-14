package io.factorialsystems.authorizationserver.model;

import lombok.*;
import java.time.LocalDateTime;
import java.util.Map;

/**
 * AuditLog entity for tracking important security and operational events.
 * Provides compliance audit trail for the multi-tenant OAuth2 system.
 */
@Getter
@Setter
@ToString
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AuditLog {
    
    /**
     * Unique audit log entry identifier (UUID)
     */
    private String id;
    
    /**
     * Tenant this event is associated with (UUID foreign key, nullable for system events)
     */
    private String tenantId;
    
    /**
     * User this event is associated with (UUID foreign key, nullable for system events)
     */
    private String userId;
    
    /**
     * Type of event that occurred
     * Examples: LOGIN, LOGOUT, LOGIN_FAILED, ROLE_ASSIGNED, ROLE_REMOVED, 
     *          USER_CREATED, USER_UPDATED, USER_DELETED, TENANT_CREATED, 
     *          PASSWORD_CHANGED, EMAIL_VERIFIED, ACCOUNT_LOCKED, OAUTH_TOKEN_ISSUED,
     *          PERMISSION_DENIED, SYSTEM_ERROR
     */
    private String eventType;
    
    /**
     * Human-readable description of what happened
     */
    private String eventDescription;
    
    /**
     * IP address from which the event originated
     */
    private String ipAddress;
    
    /**
     * User agent string from the request (for web-based events)
     */
    private String userAgent;
    
    /**
     * Additional structured data related to the event (JSON)
     * Examples: {"failed_attempts": 3}, {"old_email": "old@example.com", "new_email": "new@example.com"}
     */
    private Map<String, Object> additionalData;
    
    /**
     * When the event occurred
     */
    private LocalDateTime createdAt;
    
    // Relationships - populated by service layer
    /**
     * Tenant object (populated when needed)
     */
    private Tenant tenant;
    
    /**
     * User object (populated when needed)
     */
    private User user;
    
    // Helper methods
    
    /**
     * Check if this is a security-related event
     */
    public boolean isSecurityEvent() {
        if (eventType == null) return false;
        return eventType.contains("LOGIN") || 
               eventType.contains("PASSWORD") ||
               eventType.contains("ACCOUNT_LOCKED") ||
               eventType.contains("PERMISSION_DENIED") ||
               eventType.contains("ROLE_") ||
               eventType.contains("OAUTH");
    }
    
    /**
     * Check if this is a system-level event (not tenant-specific)
     */
    public boolean isSystemEvent() {
        return tenantId == null;
    }
    
    /**
     * Check if this is a tenant-specific event
     */
    public boolean isTenantEvent() {
        return tenantId != null;
    }
    
    /**
     * Check if this is a user-specific event
     */
    public boolean isUserEvent() {
        return userId != null;
    }
    
    /**
     * Get additional data value as string
     */
    public String getAdditionalDataValue(String key) {
        if (additionalData == null || key == null) {
            return null;
        }
        Object value = additionalData.get(key);
        return value != null ? value.toString() : null;
    }
    
    /**
     * Check if additional data contains a specific key
     */
    public boolean hasAdditionalData(String key) {
        return additionalData != null && additionalData.containsKey(key);
    }
    
    /**
     * Create a login success audit log entry
     */
    public static AuditLog createLoginSuccess(String tenantId, String userId, String ipAddress, String userAgent) {
        return AuditLog.builder()
                .tenantId(tenantId)
                .userId(userId)
                .eventType("LOGIN_SUCCESS")
                .eventDescription("User successfully logged in")
                .ipAddress(ipAddress)
                .userAgent(userAgent)
                .createdAt(LocalDateTime.now())
                .build();
    }
    
    /**
     * Create a login failure audit log entry
     */
    public static AuditLog createLoginFailure(String tenantId, String username, String ipAddress, String userAgent, String reason) {
        return AuditLog.builder()
                .tenantId(tenantId)
                .eventType("LOGIN_FAILED")
                .eventDescription(String.format("Login failed for username '%s': %s", username, reason))
                .ipAddress(ipAddress)
                .userAgent(userAgent)
                .additionalData(Map.of("username", username, "failure_reason", reason))
                .createdAt(LocalDateTime.now())
                .build();
    }
    
    /**
     * Create a role assignment audit log entry
     */
    public static AuditLog createRoleAssignment(String tenantId, String userId, String roleId, String assignedBy) {
        return AuditLog.builder()
                .tenantId(tenantId)
                .userId(userId)
                .eventType("ROLE_ASSIGNED")
                .eventDescription("Role assigned to user")
                .additionalData(Map.of("role_id", roleId, "assigned_by", assignedBy))
                .createdAt(LocalDateTime.now())
                .build();
    }
    
    /**
     * Create a user creation audit log entry
     */
    public static AuditLog createUserCreation(String tenantId, String userId, String createdBy, boolean isInvitation) {
        return AuditLog.builder()
                .tenantId(tenantId)
                .userId(userId)
                .eventType("USER_CREATED")
                .eventDescription(isInvitation ? "User created via invitation" : "User created directly")
                .additionalData(Map.of("created_by", createdBy, "via_invitation", isInvitation))
                .createdAt(LocalDateTime.now())
                .build();
    }
    
    /**
     * Create a tenant creation audit log entry
     */
    public static AuditLog createTenantCreation(String tenantId, String createdBy) {
        return AuditLog.builder()
                .tenantId(tenantId)
                .eventType("TENANT_CREATED")
                .eventDescription("New tenant created")
                .additionalData(Map.of("created_by", createdBy))
                .createdAt(LocalDateTime.now())
                .build();
    }
    
    /**
     * Create an OAuth token issued audit log entry
     */
    public static AuditLog createOAuthTokenIssued(String tenantId, String userId, String clientId, String scope, String ipAddress) {
        return AuditLog.builder()
                .tenantId(tenantId)
                .userId(userId)
                .eventType("OAUTH_TOKEN_ISSUED")
                .eventDescription("OAuth access token issued")
                .ipAddress(ipAddress)
                .additionalData(Map.of("client_id", clientId, "scope", scope))
                .createdAt(LocalDateTime.now())
                .build();
    }
    
    /**
     * Create a permission denied audit log entry
     */
    public static AuditLog createPermissionDenied(String tenantId, String userId, String resource, String action, String ipAddress) {
        return AuditLog.builder()
                .tenantId(tenantId)
                .userId(userId)
                .eventType("PERMISSION_DENIED")
                .eventDescription(String.format("Access denied to %s:%s", resource, action))
                .ipAddress(ipAddress)
                .additionalData(Map.of("resource", resource, "action", action))
                .createdAt(LocalDateTime.now())
                .build();
    }
    
    /**
     * Validate the audit log entry
     */
    public boolean isValid() {
        return eventType != null && !eventType.trim().isEmpty() &&
               eventDescription != null && !eventDescription.trim().isEmpty() &&
               createdAt != null;
    }
}