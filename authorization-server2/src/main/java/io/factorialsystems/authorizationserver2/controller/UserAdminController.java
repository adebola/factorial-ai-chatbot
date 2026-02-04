package io.factorialsystems.authorizationserver2.controller;

import io.factorialsystems.authorizationserver2.model.Role;
import io.factorialsystems.authorizationserver2.model.User;
import io.factorialsystems.authorizationserver2.service.UserService;
import io.factorialsystems.authorizationserver2.service.TenantService;
import io.factorialsystems.authorizationserver2.mapper.UserMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * Super Admin controller for cross-tenant user management
 * All endpoints require ROLE_SYSTEM_ADMIN authority
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/admin/users")
@RequiredArgsConstructor
public class UserAdminController {

    private final UserService userService;
    private final UserMapper userMapper;
    private final TenantService tenantService;
    private final PasswordEncoder passwordEncoder;

    /**
     * List all users across all tenants with pagination and filtering
     * GET /api/v1/admin/users?page=0&size=20&search=john&tenantId=xxx&role=TENANT_ADMIN
     */
    @GetMapping
    @PreAuthorize("hasAuthority('ROLE_SYSTEM_ADMIN')")
    public ResponseEntity<Map<String, Object>> listAllUsers(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size,
            @RequestParam(required = false) String search,
            @RequestParam(required = false) String tenantId,
            @RequestParam(required = false) String role,
            @RequestParam(required = false) Boolean isActive) {

        log.info("System admin listing users - page: {}, size: {}, search: {}, tenantId: {}, role: {}, isActive: {}",
                page, size, search, tenantId, role, isActive);

        // Calculate offset
        int offset = page * size;

        // Get all users
        List<User> allUsers = userMapper.findAllUsers();

        // Apply filters
        List<User> filteredUsers = allUsers.stream()
            .filter(u -> search == null || search.isEmpty() ||
                    u.getUsername().toLowerCase().contains(search.toLowerCase()) ||
                    u.getEmail().toLowerCase().contains(search.toLowerCase()) ||
                    (u.getFirstName() != null && u.getFirstName().toLowerCase().contains(search.toLowerCase())) ||
                    (u.getLastName() != null && u.getLastName().toLowerCase().contains(search.toLowerCase())))
            .filter(u -> tenantId == null || tenantId.isEmpty() || u.getTenantId().equals(tenantId))
            .filter(u -> role == null || role.isEmpty() ||
                    (u.getRoles() != null && u.getRoles().stream().anyMatch(r -> r.getName().equals(role))))
            .filter(u -> isActive == null || u.getIsActive().equals(isActive))
            .collect(Collectors.toList());

        int total = filteredUsers.size();

        // Apply pagination
        List<User> paginatedUsers = filteredUsers.stream()
            .skip(offset)
            .limit(size)
            .collect(Collectors.toList());

        // Build response
        List<Map<String, Object>> userSummaries = paginatedUsers.stream()
            .map(this::toUserSummary)
            .collect(Collectors.toList());

        Map<String, Object> response = new HashMap<>();
        response.put("users", userSummaries);
        response.put("total", total);
        response.put("page", page);
        response.put("size", size);
        response.put("totalPages", (int) Math.ceil((double) total / size));

        log.info("Returning {} users (page {} of {})", paginatedUsers.size(), page, (int) Math.ceil((double) total / size));
        return ResponseEntity.ok(response);
    }

    /**
     * Get detailed user information
     * GET /api/v1/admin/users/{id}
     */
    @GetMapping("/{id}")
    @PreAuthorize("hasAuthority('ROLE_SYSTEM_ADMIN')")
    public ResponseEntity<Map<String, Object>> getUserDetails(@PathVariable String id) {
        log.info("System admin getting user details: {}", id);

        User user = userService.findById(id);
        if (user == null) {
            log.warn("User not found: {}", id);
            return ResponseEntity.notFound().build();
        }

        // Get roles
        List<Role> roles = userMapper.findRolesByUserId(id);

        Map<String, Object> response = new HashMap<>();
        response.put("id", user.getId());
        response.put("tenantId", user.getTenantId());
        response.put("username", user.getUsername());
        response.put("email", user.getEmail());
        response.put("firstName", user.getFirstName());
        response.put("lastName", user.getLastName());
        response.put("isActive", user.getIsActive());
        response.put("isEmailVerified", user.getIsEmailVerified());
        response.put("lastLoginAt", user.getLastLoginAt());
        response.put("createdAt", user.getCreatedAt());
        response.put("updatedAt", user.getUpdatedAt());
        response.put("roles", roles.stream().map(r -> Map.of(
            "id", r.getId(),
            "name", r.getName(),
            "description", r.getDescription()
        )).collect(Collectors.toList()));

        // Get tenant info
        var tenant = tenantService.findById(user.getTenantId());
        if (tenant != null) {
            response.put("tenant", Map.of(
                "id", tenant.getId(),
                "name", tenant.getName(),
                "domain", tenant.getDomain() != null ? tenant.getDomain() : ""
            ));
        }

        log.info("User details retrieved for: {} ({} roles)", user.getUsername(), roles.size());
        return ResponseEntity.ok(response);
    }

    /**
     * Assign SYSTEM_ADMIN role to a user
     * POST /api/v1/admin/users/{id}/roles/system-admin
     */
    @PostMapping("/{id}/roles/system-admin")
    @PreAuthorize("hasAuthority('ROLE_SYSTEM_ADMIN')")
    public ResponseEntity<Map<String, Object>> assignSystemAdminRole(@PathVariable String id) {
        log.warn("System admin assigning SYSTEM_ADMIN role to user: {}", id);

        User user = userService.findById(id);
        if (user == null) {
            log.warn("User not found: {}", id);
            return ResponseEntity.notFound().build();
        }

        // Get SYSTEM_ADMIN role ID
        String systemAdminRoleId = userMapper.findRoleIdByName("SYSTEM_ADMIN");
        if (systemAdminRoleId == null) {
            log.error("SYSTEM_ADMIN role not found in the system");
            return ResponseEntity.status(500).body(Map.of("error", "SYSTEM_ADMIN role not configured"));
        }

        // Check if user already has the role
        List<Role> roles = userMapper.findRolesByUserId(id);
        boolean hasRole = roles.stream().anyMatch(r -> r.getName().equals("SYSTEM_ADMIN"));

        if (hasRole) {
            log.info("User {} already has SYSTEM_ADMIN role", user.getUsername());
            return ResponseEntity.ok(Map.of("message", "User already has SYSTEM_ADMIN role"));
        }

        // Assign role
        int result = userMapper.insertUserRole(id, systemAdminRoleId);
        if (result <= 0) {
            log.error("Failed to assign SYSTEM_ADMIN role to user {}", id);
            return ResponseEntity.status(500).body(Map.of("error", "Failed to assign role"));
        }

        Map<String, Object> response = new HashMap<>();
        response.put("id", user.getId());
        response.put("username", user.getUsername());
        response.put("email", user.getEmail());
        response.put("message", "SYSTEM_ADMIN role assigned successfully");

        log.warn("SYSTEM_ADMIN role assigned to user: {} ({})", user.getUsername(), id);
        return ResponseEntity.ok(response);
    }

    /**
     * Remove SYSTEM_ADMIN role from a user
     * DELETE /api/v1/admin/users/{id}/roles/system-admin
     */
    @DeleteMapping("/{id}/roles/system-admin")
    @PreAuthorize("hasAuthority('ROLE_SYSTEM_ADMIN')")
    public ResponseEntity<Map<String, Object>> removeSystemAdminRole(@PathVariable String id) {
        log.warn("System admin removing SYSTEM_ADMIN role from user: {}", id);

        User user = userService.findById(id);
        if (user == null) {
            log.warn("User not found: {}", id);
            return ResponseEntity.notFound().build();
        }

        // Get SYSTEM_ADMIN role ID
        String systemAdminRoleId = userMapper.findRoleIdByName("SYSTEM_ADMIN");
        if (systemAdminRoleId == null) {
            log.error("SYSTEM_ADMIN role not found in the system");
            return ResponseEntity.status(500).body(Map.of("error", "SYSTEM_ADMIN role not configured"));
        }

        // Remove role
        int result = userMapper.deleteUserRole(id, systemAdminRoleId);
        if (result <= 0) {
            log.warn("User {} did not have SYSTEM_ADMIN role or removal failed", user.getUsername());
            return ResponseEntity.ok(Map.of("message", "User did not have SYSTEM_ADMIN role"));
        }

        Map<String, Object> response = new HashMap<>();
        response.put("id", user.getId());
        response.put("username", user.getUsername());
        response.put("email", user.getEmail());
        response.put("message", "SYSTEM_ADMIN role removed successfully");

        log.warn("SYSTEM_ADMIN role removed from user: {} ({})", user.getUsername(), id);
        return ResponseEntity.ok(response);
    }

    /**
     * Suspend a user
     * POST /api/v1/admin/users/{id}/suspend
     */
    @PostMapping("/{id}/suspend")
    @PreAuthorize("hasAuthority('ROLE_SYSTEM_ADMIN')")
    public ResponseEntity<Map<String, Object>> suspendUser(@PathVariable String id) {
        log.info("System admin suspending user: {}", id);

        User user = userService.findById(id);
        if (user == null) {
            log.warn("User not found: {}", id);
            return ResponseEntity.notFound().build();
        }

        user.setIsActive(false);
        userService.updateUser(user);

        Map<String, Object> response = new HashMap<>();
        response.put("id", user.getId());
        response.put("username", user.getUsername());
        response.put("isActive", false);
        response.put("message", "User suspended successfully");

        log.warn("User suspended: {} ({})", user.getUsername(), id);
        return ResponseEntity.ok(response);
    }

    /**
     * Activate a user
     * POST /api/v1/admin/users/{id}/activate
     */
    @PostMapping("/{id}/activate")
    @PreAuthorize("hasAuthority('ROLE_SYSTEM_ADMIN')")
    public ResponseEntity<Map<String, Object>> activateUser(@PathVariable String id) {
        log.info("System admin activating user: {}", id);

        User user = userService.findById(id);
        if (user == null) {
            log.warn("User not found: {}", id);
            return ResponseEntity.notFound().build();
        }

        user.setIsActive(true);
        userService.updateUser(user);

        Map<String, Object> response = new HashMap<>();
        response.put("id", user.getId());
        response.put("username", user.getUsername());
        response.put("isActive", true);
        response.put("message", "User activated successfully");

        log.info("User activated: {} ({})", user.getUsername(), id);
        return ResponseEntity.ok(response);
    }

    /**
     * Reset user password (admin-initiated)
     * POST /api/v1/admin/users/{id}/reset-password
     */
    @PostMapping("/{id}/reset-password")
    @PreAuthorize("hasAuthority('ROLE_SYSTEM_ADMIN')")
    public ResponseEntity<Map<String, Object>> resetPassword(
            @PathVariable String id,
            @RequestBody Map<String, String> request) {

        log.info("System admin resetting password for user: {}", id);

        User user = userService.findById(id);
        if (user == null) {
            log.warn("User not found: {}", id);
            return ResponseEntity.notFound().build();
        }

        String newPassword = request.get("newPassword");
        if (newPassword == null || newPassword.length() < 8) {
            return ResponseEntity.badRequest().body(Map.of("error", "Password must be at least 8 characters"));
        }

        // Update password
        user.setPassword(passwordEncoder.encode(newPassword));
        userService.updateUser(user);

        Map<String, Object> response = new HashMap<>();
        response.put("id", user.getId());
        response.put("username", user.getUsername());
        response.put("message", "Password reset successfully");

        log.warn("Password reset by admin for user: {} ({})", user.getUsername(), id);
        return ResponseEntity.ok(response);
    }

    // Helper methods

    private Map<String, Object> toUserSummary(User user) {
        Map<String, Object> summary = new HashMap<>();
        summary.put("id", user.getId());
        summary.put("tenantId", user.getTenantId());
        summary.put("username", user.getUsername());
        summary.put("email", user.getEmail());
        summary.put("firstName", user.getFirstName());
        summary.put("lastName", user.getLastName());
        summary.put("isActive", user.getIsActive());
        summary.put("isEmailVerified", user.getIsEmailVerified());
        summary.put("lastLoginAt", user.getLastLoginAt());
        summary.put("createdAt", user.getCreatedAt());

        // Add tenant name
        var tenant = tenantService.findById(user.getTenantId());
        if (tenant != null) {
            summary.put("tenantName", tenant.getName());
        }

        // Add roles
        if (user.getRoles() != null) {
            summary.put("roles", user.getRoles().stream()
                .map(Role::getName)
                .collect(Collectors.toList()));
        }

        return summary;
    }
}
