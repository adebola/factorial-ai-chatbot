package io.factorialsystems.authorizationserver2.controller;

import io.factorialsystems.authorizationserver2.dto.TenantConfigUpdateRequest;
import io.factorialsystems.authorizationserver2.dto.TenantResponse;
import io.factorialsystems.authorizationserver2.model.Tenant;
import io.factorialsystems.authorizationserver2.model.User;
import io.factorialsystems.authorizationserver2.service.TenantService;
import io.factorialsystems.authorizationserver2.service.UserService;
import io.factorialsystems.authorizationserver2.service.RedisCacheService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

@Slf4j
@RestController
@RequestMapping("/api/v1/tenants")
@RequiredArgsConstructor
public class TenantApiController {
    
    private final TenantService tenantService;
    private final UserService userService;
    private final RedisCacheService redisCacheService;
    
    /**
     * Get tenant details by ID (for authenticated services)
     */
    @GetMapping("/{id}")
    //@PreAuthorize("hasAuthority('SCOPE_tenant:read')")
    public ResponseEntity<TenantResponse> getTenant(@PathVariable String id) {
        log.info("Getting tenant details for ID: {}", id);
        
        // Try cache first
        Tenant tenant = redisCacheService.getCachedTenant(id);
        if (tenant != null) {
            log.debug("Tenant found in cache: {}", id);
            return ResponseEntity.ok(toTenantResponse(tenant));
        }
        
        // Cache miss - fetch from database
        tenant = tenantService.findById(id);
        if (tenant == null) {
            log.warn("Tenant not found with ID: {}", id);
            return ResponseEntity.notFound().build();
        }
        
        // Cache the result
        redisCacheService.cacheTenant(tenant);
        log.debug("Tenant cached: {}", id);
        
        return ResponseEntity.ok(toTenantResponse(tenant));
    }
    
    /**
     * Public lookup for chat widget - validates an API key
     */
    @GetMapping("/lookup-by-api-key")
    public ResponseEntity<Map<String, Object>> lookupByApiKey(@RequestParam String apiKey) {
        log.info("Looking up tenant by API key");
        
        // Try cache first
        Tenant tenant = redisCacheService.getCachedTenantByApiKey(apiKey);
        if (tenant == null) {
            // Cache miss - fetch from database
            tenant = tenantService.findByApiKey(apiKey);
            if (tenant != null) {
                // Cache the result
                redisCacheService.cacheTenant(tenant);
                log.debug("Tenant cached by API key lookup: {}", tenant.getId());
            }
        } else {
            log.debug("Tenant found in cache by API key: {}", tenant.getId());
        }
        
        if (tenant == null || !tenant.getIsActive()) {
            log.warn("Tenant not found or inactive for API key");
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Map.of("error", "Tenant not found or inactive"));
        }
        
        Map<String, Object> response = new HashMap<>();
        response.put("id", tenant.getId());
        response.put("name", tenant.getName());
        response.put("domain", tenant.getDomain());
        response.put("is_active", tenant.getIsActive());
        response.put("widget_available", true);
        
        log.info("Successfully found tenant: {} for API key", tenant.getName());
        return ResponseEntity.ok(response);
    }
    
    /**
     * Update tenant configuration
     */
    @PutMapping("/{id}/config")
//    @PreAuthorize("hasAuthority('SCOPE_tenant:write')")
    public ResponseEntity<Map<String, Object>> updateTenantConfig(
            @PathVariable String id,
            @RequestBody TenantConfigUpdateRequest request) {
        
        log.info("Updating configuration for tenant: {}", id);
        
        Tenant tenant = tenantService.findById(id);
        if (tenant == null) {
            log.warn("Tenant not found with ID: {}", id);
            return ResponseEntity.notFound().build();
        }
        
        // Update config
        tenant.setConfig(request.getConfig());
        Tenant updatedTenant = tenantService.updateTenant(tenant);
        
        // Evict tenant from cache since it was updated
        redisCacheService.evictTenant(id);
        log.debug("Evicted tenant from cache after config update: {}", id);
        
        // Cache the updated tenant
        redisCacheService.cacheTenant(updatedTenant);
        log.debug("Re-cached updated tenant: {}", id);
        
        Map<String, Object> response = new HashMap<>();
        response.put("id", updatedTenant.getId());
        response.put("config", updatedTenant.getConfig());
        response.put("updated_at", updatedTenant.getUpdatedAt());
        
        log.info("Successfully updated configuration for tenant: {}", id);
        return ResponseEntity.ok(response);
    }
    
    /**
     * List users in a tenant
     */
    @GetMapping("/{id}/users")
//    @PreAuthorize("hasAuthority('SCOPE_tenant:read')")
    public ResponseEntity<Map<String, Object>> getTenantUsers(@PathVariable String id) {
        log.info("Getting users for tenant: {}", id);
        
        Tenant tenant = tenantService.findById(id);
        if (tenant == null) {
            log.warn("Tenant not found with ID: {}", id);
            return ResponseEntity.notFound().build();
        }
        
        List<User> users = userService.findByTenantId(id);
        
        Map<String, Object> response = new HashMap<>();
        response.put("tenant_id", id);
        response.put("tenant_name", tenant.getName());
        response.put("users", users.stream().map(this::toUserSummary).collect(Collectors.toList()));
        response.put("total", users.size());
        
        log.info("Found {} users for tenant: {}", users.size(), id);
        return ResponseEntity.ok(response);
    }
    
    private TenantResponse toTenantResponse(Tenant tenant) {
        return TenantResponse.builder()
                .id(tenant.getId())
                .name(tenant.getName())
                .domain(tenant.getDomain())
                .apiKey(tenant.getApiKey())
                .config(tenant.getConfig())
                .planId(tenant.getPlanId())
                .isActive(tenant.getIsActive())
                .createdAt(tenant.getCreatedAt())
                .updatedAt(tenant.getUpdatedAt())
                .build();
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