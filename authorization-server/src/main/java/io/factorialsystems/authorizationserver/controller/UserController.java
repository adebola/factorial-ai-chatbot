package io.factorialsystems.authorizationserver.controller;

import io.factorialsystems.authorizationserver.dto.UserResponse;
import io.factorialsystems.authorizationserver.mapper.RoleMapper;
import io.factorialsystems.authorizationserver.mapper.UserMapper;
import io.factorialsystems.authorizationserver.model.Role;
import io.factorialsystems.authorizationserver.model.User;
import io.factorialsystems.authorizationserver.service.MultiTenantUserDetails;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * REST controller for user management operations
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/users")
@RequiredArgsConstructor
public class UserController {
    
    private final UserMapper userMapper;
    private final RoleMapper roleMapper;
    
    /**
     * Get all users for current tenant
     * Only tenant admins can list all users in their tenant
     */
    @GetMapping
    @PreAuthorize("hasRole('TENANT_ADMIN')")
    public ResponseEntity<List<UserResponse>> getTenantUsers(Authentication authentication) {
        log.debug("Getting users for tenant");
        
        try {
            MultiTenantUserDetails userDetails = (MultiTenantUserDetails) authentication.getPrincipal();
            String tenantId = userDetails.getTenantId();
            
            List<User> users = userMapper.findByTenant(tenantId);
            List<UserResponse> userResponses = users.stream()
                    .map(this::buildUserResponse)
                    .collect(Collectors.toList());
            
            return ResponseEntity.ok(userResponses);
        } catch (Exception e) {
            log.error("Error getting tenant users", e);
            return ResponseEntity.internalServerError().build();
        }
    }
    
    /**
     * Get user by ID
     * Global admins can access any user, tenant admins can access users in their tenant
     */
    @GetMapping("/{userId}")
    @PreAuthorize("hasRole('GLOBAL_ADMIN') or hasRole('TENANT_ADMIN')")
    public ResponseEntity<UserResponse> getUserById(@PathVariable String userId, Authentication authentication) {
        log.debug("Getting user by ID: {}", userId);
        
        try {
            MultiTenantUserDetails userDetails = (MultiTenantUserDetails) authentication.getPrincipal();
            String tenantId = userDetails.getTenantId();
            
            // Global admins can access any user, tenant admins only users in their tenant
            Optional<User> userOpt;
            if (userDetails.hasRole("GLOBAL_ADMIN")) {
                // For global admin, we need to find by ID across all tenants
                // This would require a different mapper method
                userOpt = userMapper.findByIdAndTenant(userId, tenantId); // For now, same logic
            } else {
                userOpt = userMapper.findByIdAndTenant(userId, tenantId);
            }
            
            if (userOpt.isEmpty()) {
                return ResponseEntity.notFound().build();
            }
            
            UserResponse response = buildUserResponse(userOpt.get());
            return ResponseEntity.ok(response);
            
        } catch (Exception e) {
            log.error("Error getting user by ID: {}", userId, e);
            return ResponseEntity.internalServerError().build();
        }
    }
    
    /**
     * Get current user profile
     */
    @GetMapping("/me")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<UserResponse> getCurrentUser(Authentication authentication) {
        try {
            MultiTenantUserDetails userDetails = (MultiTenantUserDetails) authentication.getPrincipal();
            String userId = userDetails.getUserId();
            String tenantId = userDetails.getTenantId();
            
            Optional<User> userOpt = userMapper.findByIdAndTenant(userId, tenantId);
            if (userOpt.isEmpty()) {
                return ResponseEntity.notFound().build();
            }
            
            UserResponse response = buildUserResponse(userOpt.get());
            return ResponseEntity.ok(response);
            
        } catch (Exception e) {
            log.error("Error getting current user", e);
            return ResponseEntity.internalServerError().build();
        }
    }
    
    /**
     * Get tenant admins
     * Only tenant admins can list other admins in their tenant
     */
    @GetMapping("/admins")
    @PreAuthorize("hasRole('TENANT_ADMIN') or hasRole('GLOBAL_ADMIN')")
    public ResponseEntity<List<UserResponse>> getTenantAdmins(Authentication authentication) {
        log.debug("Getting tenant admins");
        
        try {
            MultiTenantUserDetails userDetails = (MultiTenantUserDetails) authentication.getPrincipal();
            String tenantId = userDetails.getTenantId();
            
            List<User> admins = userMapper.findTenantAdmins(tenantId);
            List<UserResponse> adminResponses = admins.stream()
                    .map(this::buildUserResponse)
                    .collect(Collectors.toList());
            
            return ResponseEntity.ok(adminResponses);
        } catch (Exception e) {
            log.error("Error getting tenant admins", e);
            return ResponseEntity.internalServerError().build();
        }
    }
    
    /**
     * Deactivate user
     * Only tenant admins can deactivate users in their tenant (except themselves)
     */
    @DeleteMapping("/{userId}")
    @PreAuthorize("hasRole('TENANT_ADMIN') and #userId != authentication.principal.userId")
    public ResponseEntity<Void> deactivateUser(@PathVariable String userId, Authentication authentication) {
        log.info("Deactivating user: {}", userId);
        
        try {
            MultiTenantUserDetails userDetails = (MultiTenantUserDetails) authentication.getPrincipal();
            String tenantId = userDetails.getTenantId();
            
            int rows = userMapper.deactivateUser(userId, tenantId);
            return rows > 0 ? ResponseEntity.noContent().build() 
                           : ResponseEntity.notFound().build();
        } catch (Exception e) {
            log.error("Error deactivating user: {}", userId, e);
            return ResponseEntity.internalServerError().build();
        }
    }
    
    /**
     * Build user response DTO
     */
    private UserResponse buildUserResponse(User user) {
        try {
            // Get user roles
            List<Role> roles = roleMapper.findByUserId(user.getId());
            
            List<UserResponse.RoleInfo> roleInfos = roles.stream()
                    .map(role -> UserResponse.RoleInfo.builder()
                            .id(role.getId())
                            .name(role.getName())
                            .description(role.getDescription())
                            .isGlobal(true) // All roles are global now
                            .isActive(role.getIsActive())
                            .build())
                    .toList(); // Use toList() instead of collect(Collectors.toList())
            
            // Get all permissions from roles
            Set<String> permissions = roles.stream()
                    .filter(role -> role.getIsActive() != null && role.getIsActive())
                    .flatMap(role -> role.getPermissions().stream())
                    .collect(Collectors.toSet());
            
            return UserResponse.builder()
                    .id(user.getId())
                    .tenantId(user.getTenantId())
                    .username(user.getUsername())
                    .email(user.getEmail())
                    .firstName(user.getFirstName())
                    .lastName(user.getLastName())
                    .fullName(user.getFullName())
                    .isActive(user.getIsActive())
                    .isTenantAdmin(user.getIsTenantAdmin())
                    .emailVerified(user.getEmailVerified())
                    .accountLocked(user.getAccountLocked())
                    .passwordExpiresAt(user.getPasswordExpiresAt())
                    .lastLoginAt(user.getLastLoginAt())
                    .failedLoginAttempts(user.getFailedLoginAttempts())
                    .lastFailedLoginAt(user.getLastFailedLoginAt())
                    .hasPendingInvitation(user.hasPendingInvitation())
                    .invitationExpiresAt(user.getInvitationExpiresAt())
                    .invitedBy(user.getInvitedBy())
                    .createdAt(user.getCreatedAt())
                    .updatedAt(user.getUpdatedAt())
                    .roles(roleInfos)
                    .permissions(permissions)
                    .build();
                    
        } catch (Exception e) {
            log.error("Error building user response for user: {}", user.getId(), e);
            throw new RuntimeException("Failed to build user response", e);
        }
    }
}