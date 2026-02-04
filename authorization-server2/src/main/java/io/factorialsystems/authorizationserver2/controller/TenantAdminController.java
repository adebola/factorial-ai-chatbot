package io.factorialsystems.authorizationserver2.controller;

import io.factorialsystems.authorizationserver2.dto.TenantResponse;
import io.factorialsystems.authorizationserver2.dto.UpdateTenantRequest;
import io.factorialsystems.authorizationserver2.model.Tenant;
import io.factorialsystems.authorizationserver2.model.User;
import io.factorialsystems.authorizationserver2.service.TenantService;
import io.factorialsystems.authorizationserver2.service.UserService;
import io.factorialsystems.authorizationserver2.service.BillingServiceClient;
import io.factorialsystems.authorizationserver2.service.ChatServiceClient;
import io.factorialsystems.authorizationserver2.service.OnboardingServiceClient;
import io.factorialsystems.authorizationserver2.mapper.TenantMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * Super Admin controller for cross-tenant management
 * All endpoints require ROLE_SYSTEM_ADMIN authority
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/admin/tenants")
@RequiredArgsConstructor
public class TenantAdminController {

    private final TenantService tenantService;
    private final TenantMapper tenantMapper;
    private final UserService userService;
    private final BillingServiceClient billingServiceClient;
    private final ChatServiceClient chatServiceClient;
    private final OnboardingServiceClient onboardingServiceClient;

    /**
     * List all tenants with pagination
     * GET /api/v1/admin/tenants?page=0&size=20&search=example
     */
    @GetMapping
    @PreAuthorize("hasAuthority('ROLE_SYSTEM_ADMIN')")
    public ResponseEntity<Map<String, Object>> listAllTenants(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size,
            @RequestParam(required = false) String search,
            @RequestParam(required = false) Boolean isActive) {

        log.info("System admin listing tenants - page: {}, size: {}, search: {}, isActive: {}",
                page, size, search, isActive);

        // Calculate offset
        int offset = page * size;

        // Get filtered tenants
        List<Tenant> allTenants = tenantMapper.findAll();

        // Apply filters
        List<Tenant> filteredTenants = allTenants.stream()
            .filter(t -> search == null || search.isEmpty() ||
                    t.getName().toLowerCase().contains(search.toLowerCase()) ||
                    (t.getDomain() != null && t.getDomain().toLowerCase().contains(search.toLowerCase())))
            .filter(t -> isActive == null || t.getIsActive().equals(isActive))
            .toList();

        int total = filteredTenants.size();

        // Apply pagination
        List<Tenant> paginatedTenants = filteredTenants.stream()
            .skip(offset)
            .limit(size)
            .toList();

        // Build response with user counts
        List<Map<String, Object>> tenantSummaries = paginatedTenants.stream()
            .map(this::toTenantSummary)
            .collect(Collectors.toList());

        Map<String, Object> response = new HashMap<>();
        response.put("tenants", tenantSummaries);
        response.put("total", total);
        response.put("page", page);
        response.put("size", size);
        response.put("totalPages", (int) Math.ceil((double) total / size));

        log.info("Returning {} tenants (page {} of {})", paginatedTenants.size(), page, (int) Math.ceil((double) total / size));
        return ResponseEntity.ok(response);
    }

    /**
     * Get simplified tenant list for dropdown selection (SYSTEM_ADMIN only).
     * Returns all active tenants without pagination - optimized for UI dropdowns.
     *
     * GET /api/v1/admin/tenants/dropdown
     *
     * @return List of active tenants with id and name only, sorted alphabetically
     */
    @GetMapping("/dropdown")
    @PreAuthorize("hasAuthority('ROLE_SYSTEM_ADMIN')")
    public ResponseEntity<List<Map<String, String>>> getTenantsForDropdown() {
        log.info("System admin requesting tenant dropdown list");

        // Get all tenants from database
        List<Tenant> allTenants = tenantMapper.findAll();

        // Filter to active tenants only and map to simple id/name pairs
        List<Map<String, String>> tenantOptions = allTenants.stream()
            .filter(Tenant::getIsActive)  // Only include active tenants
            .sorted((t1, t2) -> t1.getName().compareToIgnoreCase(t2.getName()))  // Sort alphabetically
            .map(tenant -> {
                Map<String, String> option = new HashMap<>();
                option.put("id", tenant.getId());
                option.put("name", tenant.getName());
                return option;
            })
            .collect(Collectors.toList());

        log.info("Returning {} active tenants for dropdown", tenantOptions.size());
        return ResponseEntity.ok(tenantOptions);
    }

    /**
     * Get detailed tenant information
     * GET /api/v1/admin/tenants/{id}
     */
    @GetMapping("/{id}")
    @PreAuthorize("hasAuthority('ROLE_SYSTEM_ADMIN')")
    public ResponseEntity<Map<String, Object>> getTenantDetails(@PathVariable String id) {
        log.info("System admin getting tenant details: {}", id);

        Tenant tenant = tenantService.findById(id);
        if (tenant == null) {
            log.warn("Tenant not found: {}", id);
            return ResponseEntity.notFound().build();
        }

        // Get users for this tenant
        List<User> users = userService.findByTenantId(id);

        Map<String, Object> response = new HashMap<>();
        response.put("id", tenant.getId());
        response.put("name", tenant.getName());
        response.put("domain", tenant.getDomain());
        response.put("apiKey", tenant.getApiKey());
        response.put("config", tenant.getConfig());
        response.put("planId", tenant.getPlanId());
        response.put("subscriptionId", tenant.getSubscriptionId());
        response.put("isActive", tenant.getIsActive());
        response.put("createdAt", tenant.getCreatedAt());
        response.put("updatedAt", tenant.getUpdatedAt());
        response.put("userCount", users.size());
        response.put("users", users.stream().map(this::toUserSummary).collect(Collectors.toList()));

        log.info("Tenant details retrieved for: {} ({} users)", tenant.getName(), users.size());
        return ResponseEntity.ok(response);
    }

    /**
     * Update tenant information
     * PUT /api/v1/admin/tenants/{id}
     */
    @PutMapping("/{id}")
    @PreAuthorize("hasAuthority('ROLE_SYSTEM_ADMIN')")
    public ResponseEntity<Map<String, Object>> updateTenant(
            @PathVariable String id,
            @RequestBody UpdateTenantRequest request) {

        log.info("System admin updating tenant: {}", id);

        Tenant tenant = tenantService.findById(id);
        if (tenant == null) {
            log.warn("Tenant not found: {}", id);
            return ResponseEntity.notFound().build();
        }

        // Update fields if provided
        if (request.getName() != null) {
            tenant.setName(request.getName());
        }
        if (request.getDomain() != null) {
            tenant.setDomain(request.getDomain());
        }
        if (request.getConfig() != null) {
            tenant.setConfig(request.getConfig());
        }
        if (request.getPlanId() != null) {
            tenant.setPlanId(request.getPlanId());
        }

        // Update in database (updateTenant sets updatedAt automatically)
        tenantService.updateTenant(tenant);

        Map<String, Object> response = new HashMap<>();
        response.put("id", tenant.getId());
        response.put("name", tenant.getName());
        response.put("domain", tenant.getDomain());
        response.put("isActive", tenant.getIsActive());
        response.put("updatedAt", tenant.getUpdatedAt());
        response.put("message", "Tenant updated successfully");

        log.info("Tenant updated: {}", tenant.getName());
        return ResponseEntity.ok(response);
    }

    /**
     * Suspend a tenant
     * POST /api/v1/admin/tenants/{id}/suspend
     */
    @PostMapping("/{id}/suspend")
    @PreAuthorize("hasAuthority('ROLE_SYSTEM_ADMIN')")
    public ResponseEntity<Map<String, Object>> suspendTenant(@PathVariable String id) {
        log.info("System admin suspending tenant: {}", id);

        Tenant tenant = tenantService.findById(id);
        if (tenant == null) {
            log.warn("Tenant not found: {}", id);
            return ResponseEntity.notFound().build();
        }

        tenant.setIsActive(false);
        tenantService.updateTenant(tenant);

        Map<String, Object> response = new HashMap<>();
        response.put("id", tenant.getId());
        response.put("name", tenant.getName());
        response.put("isActive", false);
        response.put("message", "Tenant suspended successfully");

        log.warn("Tenant suspended: {} ({})", tenant.getName(), id);
        return ResponseEntity.ok(response);
    }

    /**
     * Activate a tenant
     * POST /api/v1/admin/tenants/{id}/activate
     */
    @PostMapping("/{id}/activate")
    @PreAuthorize("hasAuthority('ROLE_SYSTEM_ADMIN')")
    public ResponseEntity<Map<String, Object>> activateTenant(@PathVariable String id) {
        log.info("System admin activating tenant: {}", id);

        Tenant tenant = tenantService.findById(id);
        if (tenant == null) {
            log.warn("Tenant not found: {}", id);
            return ResponseEntity.notFound().build();
        }

        tenant.setIsActive(true);
        tenantService.updateTenant(tenant);

        Map<String, Object> response = new HashMap<>();
        response.put("id", tenant.getId());
        response.put("name", tenant.getName());
        response.put("isActive", true);
        response.put("message", "Tenant activated successfully");

        log.info("Tenant activated: {} ({})", tenant.getName(), id);
        return ResponseEntity.ok(response);
    }

    /**
     * Get tenant subscription details
     * GET /api/v1/admin/tenants/{id}/subscription
     */
    @GetMapping("/{id}/subscription")
    @PreAuthorize("hasAuthority('ROLE_SYSTEM_ADMIN')")
    public ResponseEntity<Map<String, Object>> getTenantSubscription(
            @PathVariable String id,
            @RequestHeader("Authorization") String authorizationHeader) {
        log.info("System admin getting subscription for tenant: {}", id);

        Tenant tenant = tenantService.findById(id);
        if (tenant == null) {
            log.warn("Tenant not found: {}", id);
            return ResponseEntity.notFound().build();
        }

        try {
            // Fetch subscription from billing service by tenant ID
            Map<String, Object> subscription = billingServiceClient.getSubscriptionByTenant(id, authorizationHeader);

            Map<String, Object> response = new HashMap<>();
            response.put("tenant_id", id);
            response.put("tenant_name", tenant.getName());
            response.put("subscription", subscription);

            return ResponseEntity.ok(response);
        } catch (RuntimeException e) {
            // Handle 404 from billing service gracefully
            if (e.getMessage() != null && e.getMessage().contains("HTTP 404")) {
                log.warn("Subscription not found in billing service for tenant {} (subscription_id: {})",
                    id, tenant.getSubscriptionId());
                Map<String, Object> response = new HashMap<>();
                response.put("tenant_id", id);
                response.put("tenant_name", tenant.getName());
                response.put("subscription_id", tenant.getSubscriptionId());
                response.put("message", "Subscription not found in billing service");
                response.put("note", "This tenant may need to create a subscription");
                return ResponseEntity.ok(response);
            }

            // Other errors return 500
            log.error("Error fetching subscription for tenant {}: {}", id, e.getMessage());
            Map<String, Object> response = new HashMap<>();
            response.put("error", "Failed to fetch subscription details");
            return ResponseEntity.status(500).body(response);
        } catch (Exception e) {
            log.error("Unexpected error fetching subscription for tenant {}: {}", id, e.getMessage());
            Map<String, Object> response = new HashMap<>();
            response.put("error", "Failed to fetch subscription details");
            return ResponseEntity.status(500).body(response);
        }
    }

    /**
     * Get tenant statistics
     * GET /api/v1/admin/tenants/{id}/statistics
     */
    @GetMapping("/{id}/statistics")
    @PreAuthorize("hasAuthority('ROLE_SYSTEM_ADMIN')")
    public ResponseEntity<Map<String, Object>> getTenantStatistics(
            @PathVariable String id,
            @RequestHeader("Authorization") String authorizationHeader) {
        log.info("System admin getting statistics for tenant: {}", id);

        Tenant tenant = tenantService.findById(id);
        if (tenant == null) {
            log.warn("Get Tenant Statistics: Tenant not found: {}", id);
            return ResponseEntity.notFound().build();
        }

        // Get user statistics (local to authorization server)
        List<User> users = userService.findByTenantId(id);
        long totalUsers = users.size();
        long activeUsers = users.stream().filter(User::getIsActive).count();

        // Get last activity from most recent user login
        String lastActivity = users.stream()
            .map(User::getLastLoginAt)
            .filter(java.util.Objects::nonNull)
            .max(java.time.OffsetDateTime::compareTo)
            .map(java.time.OffsetDateTime::toString)
            .orElse(null);

        // Get chat statistics from the chat service (with graceful degradation)
        long totalChats = 0;
        long totalMessages = 0;
        try {
            Map<String, Object> chatStats = chatServiceClient.getChatStats(id, authorizationHeader);
            totalChats = getLongValue(chatStats, "total_sessions");
            totalMessages = getLongValue(chatStats, "total_messages");
            log.debug("Retrieved chat stats for tenant {}: {} chats, {} messages", id, totalChats, totalMessages);
        } catch (Exception e) {
            log.error("Failed to fetch chat stats for tenant {}: {}", id, e.getMessage());
            // Continue with zeros - graceful degradation
        }

        // Get onboarding statistics from onboarding service (with graceful degradation)
        long numDocuments = 0;
        long numWebsites = 0;
        double storageUsedMb = 0;
        try {
            Map<String, Object> onboardingStats = onboardingServiceClient.getOnboardingStats(id, authorizationHeader);
            numDocuments = getLongValue(onboardingStats, "num_documents");
            numWebsites = getLongValue(onboardingStats, "num_websites");
            storageUsedMb = getDoubleValue(onboardingStats, "storage_used_mb");
            log.debug("Retrieved onboarding stats for tenant {}: {} docs, {} websites, {} MB",
                id, numDocuments, numWebsites, storageUsedMb);
        } catch (Exception e) {
            log.error("Failed to fetch onboarding stats for tenant {}: {}", id, e.getMessage());
            // Continue with zeros - graceful degradation
        }

        // Build response
        Map<String, Object> response = new HashMap<>();
        response.put("total_users", totalUsers);
        response.put("active_users", activeUsers);
        response.put("total_chats", totalChats);
        response.put("total_messages", totalMessages);
        response.put("num_documents", numDocuments);
        response.put("num_websites", numWebsites);
        response.put("storage_used_mb", storageUsedMb);
        response.put("last_activity", lastActivity);

        log.info("Statistics for tenant {}: {} users ({} active), {} chats, {} messages, {} docs, {} websites",
            tenant.getName(), totalUsers, activeUsers, totalChats, totalMessages, numDocuments, numWebsites);
        return ResponseEntity.ok(response);
    }

    /**
     * Helper method to safely extract long values from a map
     */
    private long getLongValue(Map<String, Object> map, String key) {
        Object value = map.get(key);
        if (value instanceof Number) {
            return ((Number) value).longValue();
        }
        return 0;
    }

    /**
     * Helper method to safely extract double values from a map
     */
    private double getDoubleValue(Map<String, Object> map, String key) {
        Object value = map.get(key);
        if (value instanceof Number) {
            return ((Number) value).doubleValue();
        }
        return 0.0;
    }

    // Helper methods

    private Map<String, Object> toTenantSummary(Tenant tenant) {
        Map<String, Object> summary = new HashMap<>();
        summary.put("id", tenant.getId());
        summary.put("name", tenant.getName());
        summary.put("domain", tenant.getDomain());
        summary.put("planId", tenant.getPlanId());
        summary.put("isActive", tenant.getIsActive());
        summary.put("createdAt", tenant.getCreatedAt());
        summary.put("updatedAt", tenant.getUpdatedAt());

        // Get user count
        List<User> users = userService.findByTenantId(tenant.getId());
        summary.put("userCount", users.size());

        return summary;
    }

    private Map<String, Object> toUserSummary(User user) {
        Map<String, Object> summary = new HashMap<>();
        summary.put("id", user.getId());
        summary.put("username", user.getUsername());
        summary.put("email", user.getEmail());
        summary.put("firstName", user.getFirstName());
        summary.put("lastName", user.getLastName());
        summary.put("isActive", user.getIsActive());
        summary.put("lastLoginAt", user.getLastLoginAt());
        return summary;
    }
}
