package io.factorialsystems.authorizationserver.model;

import lombok.*;

import java.time.LocalDateTime;
import java.util.List;

/**
 * Role entity representing global system roles with permissions.
 * Simplified model - all roles are global and shared across all tenants.
 */
@Getter
@Setter
@ToString
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class Role {
    
    /**
     * Unique role identifier (UUID)
     */
    private String id;
    
    /**
     * Role name (e.g., ADMIN, USER, VIEWER)
     * Simple global role names without prefixes
     */
    private String name;
    
    /**
     * Human-readable description of the role
     */
    private String description;
    
    /**
     * JSON array of permission strings
     * Examples: ["documents:read", "users:manage", "system:admin"]
     */
    private List<String> permissions;
    
    /**
     * Whether the role is active and can be assigned
     */
    private Boolean isActive;
    
    // Audit fields
    /**
     * When the role was created
     */
    private LocalDateTime createdAt;
    
    /**
     * When the role was last updated
     */
    private LocalDateTime updatedAt;
    
    // Helper methods
    
    /**
     * Check if this role has a specific permission
     */
    public boolean hasPermission(String permission) {
        return permissions != null && permissions.contains(permission);
    }
    
    /**
     * Check if this role has any permission that starts with a given prefix
     */
    public boolean hasPermissionStartingWith(String prefix) {
        if (permissions == null) {
            return false;
        }
        return permissions.stream().anyMatch(perm -> perm.startsWith(prefix));
    }
    
    /**
     * Check if this is an admin role
     */
    public boolean isAdmin() {
        return name != null && name.equals("ADMIN");
    }
    
    /**
     * Check if this role can be assigned to users
     */
    public boolean canBeAssigned() {
        return isActive != null && isActive && 
               permissions != null && !permissions.isEmpty();
    }
    
    /**
     * Get all permissions (simplified - no inheritance since we removed parent roles)
     */
    public List<String> getAllPermissions() {
        return permissions != null ? List.copyOf(permissions) : List.of();
    }
    
    /**
     * Validate role constraints
     */
    public boolean isValid() {
        // Role name is required
        if (name == null || name.trim().isEmpty()) {
            return false;
        }
        
        // Permissions array should not be empty
        return permissions != null && !permissions.isEmpty();
    }
    
    /**
     * Check if user has admin permissions (system management)
     */
    public boolean hasAdminPermissions() {
        return hasPermission("system:manage") || hasPermissionStartingWith("users:");
    }
    
    /**
     * Check if user can manage documents
     */
    public boolean canManageDocuments() {
        return hasPermission("documents:manage") || 
               (hasPermission("documents:create") && hasPermission("documents:delete"));
    }
    
    /**
     * Get a user-friendly role display name
     */
    public String getDisplayName() {
        if (name == null) {
            return "Unknown Role";
        }
        
        return switch (name) {
            case "ADMIN" -> "Administrator";
            case "USER" -> "User";  
            case "VIEWER" -> "Viewer";
            default -> name; // Return the name as-is for custom roles
        };
    }
}