package io.factorialsystems.authorizationserver2.controller;

import io.factorialsystems.authorizationserver2.dto.ChangePasswordRequest;
import io.factorialsystems.authorizationserver2.dto.UserProfileUpdateRequest;
import io.factorialsystems.authorizationserver2.dto.UserResponse;
import io.factorialsystems.authorizationserver2.model.User;
import io.factorialsystems.authorizationserver2.service.UserService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.web.bind.annotation.*;

import jakarta.validation.Valid;
import java.util.HashMap;
import java.util.Map;

@Slf4j
@RestController
@RequestMapping("/api/v1/users")
@RequiredArgsConstructor
public class UserApiController {
    
    private final UserService userService;
    
    /**
     * Get current user info from JWT token
     */
    @GetMapping("/me")
    @PreAuthorize("hasAuthority('SCOPE_user:read')")
    public ResponseEntity<UserResponse> getCurrentUser(Authentication authentication) {
        log.info("Getting current user info");
        
        String userId = extractUserIdFromToken(authentication);
        if (userId == null) {
            log.warn("Unable to extract user ID from token");
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build();
        }
        
        User user = userService.findById(userId);
        if (user == null) {
            log.warn("User not found with ID: {}", userId);
            return ResponseEntity.notFound().build();
        }
        
        return ResponseEntity.ok(toUserResponse(user));
    }
    
    /**
     * Get user details by ID
     */
    @GetMapping("/{id}")
    @PreAuthorize("hasAuthority('SCOPE_user:read')")
    public ResponseEntity<UserResponse> getUser(@PathVariable String id) {
        log.info("Getting user details for ID: {}", id);
        
        User user = userService.findById(id);
        if (user == null) {
            log.warn("User not found with ID: {}", id);
            return ResponseEntity.notFound().build();
        }
        
        return ResponseEntity.ok(toUserResponse(user));
    }
    
    /**
     * Update user profile
     */
    @PutMapping("/{id}/profile")
    @PreAuthorize("hasAuthority('SCOPE_user:write')")
    public ResponseEntity<UserResponse> updateUserProfile(
            @PathVariable String id,
            @RequestBody UserProfileUpdateRequest request,
            Authentication authentication) {
        
        log.info("Updating profile for user: {}", id);
        
        // Verify the user is updating their own profile or has admin access
        String currentUserId = extractUserIdFromToken(authentication);
        if (!id.equals(currentUserId)) {
            log.warn("User {} attempted to update profile of user {}", currentUserId, id);
            return ResponseEntity.status(HttpStatus.FORBIDDEN).build();
        }
        
        User user = userService.findById(id);
        if (user == null) {
            log.warn("User not found with ID: {}", id);
            return ResponseEntity.notFound().build();
        }
        
        // Update profile fields
        if (request.getFirstName() != null) {
            user.setFirstName(request.getFirstName().trim());
        }
        if (request.getLastName() != null) {
            user.setLastName(request.getLastName().trim());
        }
        
        User updatedUser = userService.updateUser(user);
        log.info("Successfully updated profile for user: {}", id);
        
        return ResponseEntity.ok(toUserResponse(updatedUser));
    }
    
    /**
     * Change password
     */
    @PostMapping("/change-password")
    @PreAuthorize("hasAuthority('SCOPE_user:write')")
    public ResponseEntity<Map<String, Object>> changePassword(
            @Valid @RequestBody ChangePasswordRequest request,
            Authentication authentication) {
        
        log.info("Processing password change request");
        
        String userId = extractUserIdFromToken(authentication);
        if (userId == null) {
            log.warn("Unable to extract user ID from token for password change");
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .body(Map.of("error", "Invalid authentication token"));
        }
        
        try {
            userService.changePassword(userId, request.getCurrentPassword(), request.getNewPassword());
            
            Map<String, Object> response = new HashMap<>();
            response.put("message", "Password changed successfully");
            response.put("timestamp", java.time.OffsetDateTime.now());
            
            log.info("Password changed successfully for user: {}", userId);
            return ResponseEntity.ok(response);
            
        } catch (IllegalArgumentException e) {
            log.warn("Password change failed for user {}: {}", userId, e.getMessage());
            return ResponseEntity.badRequest()
                .body(Map.of("error", e.getMessage()));
        } catch (Exception e) {
            log.error("Unexpected error during password change for user {}: {}", userId, e.getMessage(), e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(Map.of("error", "An error occurred while changing password"));
        }
    }
    
    private String extractUserIdFromToken(Authentication authentication) {
        if (authentication instanceof JwtAuthenticationToken jwtToken) {
            return jwtToken.getToken().getClaimAsString("sub");
        }
        return null;
    }
    
    private UserResponse toUserResponse(User user) {
        return UserResponse.builder()
                .id(user.getId())
                .tenantId(user.getTenantId())
                .username(user.getUsername())
                .email(user.getEmail())
                .firstName(user.getFirstName())
                .lastName(user.getLastName())
                .isActive(user.getIsActive())
                .isEmailVerified(user.getIsEmailVerified())
                .lastLoginAt(user.getLastLoginAt())
                .createdAt(user.getCreatedAt())
                .updatedAt(user.getUpdatedAt())
                .build();
    }
}