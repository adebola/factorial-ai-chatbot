package io.factorialsystems.authorizationserver.model;

import com.fasterxml.jackson.annotation.JsonIgnore;
import lombok.*;
import java.time.LocalDateTime;
import java.util.Collection;
import java.util.List;
import java.util.stream.Stream;

/**
 * User entity representing individual users within tenants.
 * Users are tenant-scoped with unique username/email per tenant.
 */
@Getter
@Setter
@ToString
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class User {
    
    /**
     * Unique user identifier (UUID)
     */
    private String id;
    
    /**
     * Tenant this user belongs to (UUID foreign key)
     */
    private String tenantId;
    
    /**
     * Username (unique within tenant)
     */
    private String username;
    
    /**
     * Email address (unique within tenant)
     */
    private String email;
    
    /**
     * BCrypt hashed password
     */
    @JsonIgnore
    private String passwordHash;
    
    // Personal information
    /**
     * User's first name
     */
    private String firstName;
    
    /**
     * User's last name
     */
    private String lastName;
    
    // Account status
    /**
     * Whether the user account is active
     */
    private Boolean isActive;
    
    /**
     * Whether the user is a tenant administrator
     * First user in tenant automatically becomes admin
     */
    private Boolean isTenantAdmin;
    
    /**
     * Whether the user's email has been verified
     */
    private Boolean emailVerified;
    
    /**
     * Whether the user account is locked (security measure)
     */
    private Boolean accountLocked;
    
    /**
     * When the user's password expires (optional)
     */
    private LocalDateTime passwordExpiresAt;
    
    // Invitation system
    /**
     * Secure token for email invitation flow
     */
    @JsonIgnore
    private String invitationToken;
    
    /**
     * When the invitation token expires
     */
    private LocalDateTime invitationExpiresAt;
    
    /**
     * User ID who invited this user
     */
    private String invitedBy;
    
    // Login tracking
    /**
     * Last successful login timestamp
     */
    private LocalDateTime lastLoginAt;
    
    /**
     * Number of consecutive failed login attempts
     */
    private Integer failedLoginAttempts;
    
    /**
     * Timestamp of last failed login attempt
     */
    private LocalDateTime lastFailedLoginAt;
    
    // Audit fields
    /**
     * When the user was created
     */
    private LocalDateTime createdAt;
    
    /**
     * When the user was last updated
     */
    private LocalDateTime updatedAt;
    
    // Relationships - populated by service layer
    /**
     * Tenant object (populated when needed)
     */
    private Tenant tenant;
    
    /**
     * User roles (populated when needed)
     */
    private List<Role> roles;
    
    // Helper methods
    
    /**
     * Get the user's full name
     */
    public String getFullName() {
        if (firstName == null && lastName == null) {
            return username;
        }
        StringBuilder fullName = new StringBuilder();
        if (firstName != null && !firstName.trim().isEmpty()) {
            fullName.append(firstName.trim());
        }
        if (lastName != null && !lastName.trim().isEmpty()) {
            if (!fullName.isEmpty()) {
                fullName.append(" ");
            }
            fullName.append(lastName.trim());
        }
        return !fullName.isEmpty() ? fullName.toString() : username;
    }
    
    /**
     * Check if the user account is enabled and ready for authentication
     */
    public boolean isAccountNonExpired() {
        return passwordExpiresAt == null || passwordExpiresAt.isAfter(LocalDateTime.now());
    }
    
    /**
     * Check if the user account is not locked
     */
    public boolean isAccountNonLocked() {
        return accountLocked == null || !accountLocked;
    }
    
    /**
     * Check if user credentials are non-expired
     */
    public boolean isCredentialsNonExpired() {
        return isAccountNonExpired();
    }
    
    /**
     * Check if the user is enabled (active and verified)
     */
    public boolean isEnabled() {
        return isActive != null && isActive && 
               emailVerified != null && emailVerified;
    }
    
    /**
     * Check if the user has a pending invitation
     */
    public boolean hasPendingInvitation() {
        return invitationToken != null && !invitationToken.trim().isEmpty() &&
               invitationExpiresAt != null && invitationExpiresAt.isAfter(LocalDateTime.now()) &&
               passwordHash == null; // Password not set yet
    }
    
    /**
     * Check if the user can be authenticated
     */
    public boolean canAuthenticate() {
        return !isEnabled() || !isAccountNonLocked() || !isCredentialsNonExpired() ||
                passwordHash == null || passwordHash.trim().isEmpty();
    }
    
    /**
     * Reset failed login attempts (called on successful login)
     */
    public void resetFailedLoginAttempts() {
        this.failedLoginAttempts = 0;
        this.lastFailedLoginAt = null;
        this.lastLoginAt = LocalDateTime.now();
    }
    
    /**
     * Increment failed login attempts
     */
    public void incrementFailedLoginAttempts() {
        this.failedLoginAttempts = (this.failedLoginAttempts == null) ? 1 : this.failedLoginAttempts + 1;
        this.lastFailedLoginAt = LocalDateTime.now();
        
        // Auto-lock after 5 failed attempts
        if (this.failedLoginAttempts >= 5) {
            this.accountLocked = true;
        }
    }
    
    /**
     * Get all permission strings from user roles
     */
    public Collection<String> getAllPermissions() {
        if (roles == null) {
            return List.of();
        }
        return roles.stream()
                .filter(role -> role.getIsActive() != null && role.getIsActive())
                .flatMap(role -> role.getPermissions() != null ? role.getPermissions().stream() : Stream.empty())
                .distinct()
                .toList();
    }
}