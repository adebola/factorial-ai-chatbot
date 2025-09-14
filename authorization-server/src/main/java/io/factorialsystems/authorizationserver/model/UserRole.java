package io.factorialsystems.authorizationserver.model;

import lombok.*;

import java.time.LocalDateTime;

/**
 * UserRole entity representing the many-to-many assignment of roles to users.
 * Includes audit trail and optional role expiration.
 */
@Getter
@Setter
@ToString
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class UserRole {
    
    /**
     * Unique user role assignment identifier (UUID)
     */
    private String id;
    
    /**
     * User ID this role is assigned to (UUID foreign key)
     */
    private String userId;
    
    /**
     * Role ID being assigned (UUID foreign key)
     */
    private String roleId;
    
    // Assignment metadata
    /**
     * When this role assignment was created
     */
    private LocalDateTime assignedAt;
    
    /**
     * User ID who assigned this role (for audit trail)
     */
    private String assignedBy;
    
    /**
     * Optional expiration time for temporary role assignments
     */
    private LocalDateTime expiresAt;
    
    /**
     * Whether this role assignment is active
     */
    private Boolean isActive;
    
    // Relationships - populated by service layer
    /**
     * User object (populated when needed)
     */
    private User user;
    
    /**
     * Role object (populated when needed)
     */
    private Role role;
    
    /**
     * User who assigned this role (populated when needed)
     */
    private User assignedByUser;
    
    // Helper methods
    
    /**
     * Check if this role assignment is currently valid and active
     */
    public boolean isCurrentlyActive() {
        return isActive != null && isActive && !isExpired();
    }
    
    /**
     * Check if this role assignment has expired
     */
    public boolean isExpired() {
        return expiresAt != null && expiresAt.isBefore(LocalDateTime.now());
    }
    
    /**
     * Check if this is a permanent role assignment (no expiration)
     */
    public boolean isPermanent() {
        return expiresAt == null;
    }
    
    /**
     * Get the remaining time until expiration (null if permanent)
     */
    public Long getRemainingDays() {
        if (expiresAt == null) {
            return null;
        }
        LocalDateTime now = LocalDateTime.now();
        if (expiresAt.isBefore(now)) {
            return 0L; // Already expired
        }
        return java.time.Duration.between(now, expiresAt).toDays();
    }
    
    /**
     * Check if this role assignment was made by the system
     */
    public boolean isSystemAssigned() {
        return assignedBy == null;
    }
    
    /**
     * Deactivate this role assignment
     */
    public void deactivate() {
        this.isActive = false;
    }
    
    /**
     * Activate this role assignment (if not expired)
     */
    public void activate() {
        if (!isExpired()) {
            this.isActive = true;
        }
    }
    
    /**
     * Extend the expiration date by specified days
     */
    public void extendExpiration(long days) {
        if (expiresAt != null) {
            this.expiresAt = this.expiresAt.plusDays(days);
        } else {
            // If it was permanent, make it expire in the specified days
            this.expiresAt = LocalDateTime.now().plusDays(days);
        }
    }
    
    /**
     * Make this role assignment permanent (remove expiration)
     */
    public void makePermanent() {
        this.expiresAt = null;
    }
    
    /**
     * Create a new temporary role assignment
     */
    public static UserRole createTemporary(String userId, String roleId, String assignedBy, long daysValid) {
        return UserRole.builder()
                .userId(userId)
                .roleId(roleId)
                .assignedBy(assignedBy)
                .assignedAt(LocalDateTime.now())
                .expiresAt(LocalDateTime.now().plusDays(daysValid))
                .isActive(true)
                .build();
    }
    
    /**
     * Create a new permanent role assignment
     */
    public static UserRole createPermanent(String userId, String roleId, String assignedBy) {
        return UserRole.builder()
                .userId(userId)
                .roleId(roleId)
                .assignedBy(assignedBy)
                .assignedAt(LocalDateTime.now())
                .expiresAt(null) // Permanent
                .isActive(true)
                .build();
    }
    
    /**
     * Validate the role assignment
     */
    public boolean isValid() {
        return userId != null && !userId.trim().isEmpty() &&
               roleId != null && !roleId.trim().isEmpty() &&
               assignedAt != null;
    }
}