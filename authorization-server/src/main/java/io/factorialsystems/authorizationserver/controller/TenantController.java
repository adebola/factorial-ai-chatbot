package io.factorialsystems.authorizationserver.controller;

import io.factorialsystems.authorizationserver.dto.TenantCreateRequest;
import io.factorialsystems.authorizationserver.dto.TenantResponse;
import io.factorialsystems.authorizationserver.service.TenantService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Optional;

/**
 * REST controller for tenant management operations
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/tenants")
@RequiredArgsConstructor
public class TenantController {
    
    private final TenantService tenantService;
    
    /**
     * Create a new tenant
     * Only global admins can create tenants
     */
    @PostMapping
    @PreAuthorize("hasRole('GLOBAL_ADMIN')")
    public ResponseEntity<TenantResponse> createTenant(@Valid @RequestBody TenantCreateRequest request) {
        log.info("Creating new tenant: {}", request.getName());
        
        try {
            TenantResponse response = tenantService.createTenant(request);
            return ResponseEntity.status(HttpStatus.CREATED).body(response);
        } catch (IllegalArgumentException e) {
            log.warn("Invalid tenant creation request: {}", e.getMessage());
            return ResponseEntity.badRequest().build();
        } catch (Exception e) {
            log.error("Error creating tenant: {}", request.getName(), e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).build();
        }
    }
    
    /**
     * Get all tenants
     * Only global admins can list all tenants
     */
    @GetMapping
    @PreAuthorize("hasRole('GLOBAL_ADMIN')")
    public ResponseEntity<List<TenantResponse>> getAllTenants() {
        log.debug("Getting all tenants");
        
        try {
            List<TenantResponse> tenants = tenantService.getAllTenants();
            return ResponseEntity.ok(tenants);
        } catch (Exception e) {
            log.error("Error getting all tenants", e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).build();
        }
    }
    
    /**
     * Get tenant by ID
     * Global admins can access any tenant, tenant admins can only access their own tenant
     */
    @GetMapping("/{tenantId}")
    @PreAuthorize("hasRole('GLOBAL_ADMIN') or (hasRole('TENANT_ADMIN') and #tenantId == authentication.principal.tenantId)")
    public ResponseEntity<TenantResponse> getTenantById(@PathVariable String tenantId) {
        log.debug("Getting tenant by ID: {}", tenantId);
        
        try {
            Optional<TenantResponse> tenant = tenantService.getTenantById(tenantId);
            return tenant.map(ResponseEntity::ok)
                         .orElse(ResponseEntity.notFound().build());
        } catch (Exception e) {
            log.error("Error getting tenant by ID: {}", tenantId, e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).build();
        }
    }
    
    /**
     * Update tenant
     * Global admins can update any tenant, tenant admins can only update their own tenant
     */
    @PutMapping("/{tenantId}")
    @PreAuthorize("hasRole('GLOBAL_ADMIN') or (hasRole('TENANT_ADMIN') and #tenantId == authentication.principal.tenantId)")
    public ResponseEntity<TenantResponse> updateTenant(@PathVariable String tenantId, 
                                                      @Valid @RequestBody TenantCreateRequest request) {
        log.info("Updating tenant: {}", tenantId);
        
        try {
            Optional<TenantResponse> response = tenantService.updateTenant(tenantId, request);
            return response.map(ResponseEntity::ok)
                          .orElse(ResponseEntity.notFound().build());
        } catch (IllegalArgumentException e) {
            log.warn("Invalid tenant update request: {}", e.getMessage());
            return ResponseEntity.badRequest().build();
        } catch (Exception e) {
            log.error("Error updating tenant: {}", tenantId, e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).build();
        }
    }
    
    /**
     * Deactivate tenant
     * Only global admins can deactivate tenants
     */
    @DeleteMapping("/{tenantId}")
    @PreAuthorize("hasRole('GLOBAL_ADMIN')")
    public ResponseEntity<Void> deactivateTenant(@PathVariable String tenantId) {
        log.info("Deactivating tenant: {}", tenantId);
        
        try {
            boolean success = tenantService.deactivateTenant(tenantId);
            return success ? ResponseEntity.noContent().build() 
                          : ResponseEntity.notFound().build();
        } catch (Exception e) {
            log.error("Error deactivating tenant: {}", tenantId, e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).build();
        }
    }
    
    /**
     * Get current tenant (for tenant-specific operations)
     * Returns the tenant that the authenticated user belongs to
     */
    @GetMapping("/current")
    @PreAuthorize("hasRole('TENANT_ADMIN') or hasRole('TENANT_USER')")
    public ResponseEntity<TenantResponse> getCurrentTenant(org.springframework.security.core.Authentication authentication) {
        try {
            if (authentication.getPrincipal() instanceof io.factorialsystems.authorizationserver.service.MultiTenantUserDetails userDetails) {
                String tenantId = userDetails.getTenantId();
                Optional<TenantResponse> tenant = tenantService.getTenantById(tenantId);
                return tenant.map(ResponseEntity::ok)
                             .orElse(ResponseEntity.notFound().build());
            } else {
                log.warn("Invalid authentication principal type");
                return ResponseEntity.badRequest().build();
            }
        } catch (Exception e) {
            log.error("Error getting current tenant", e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).build();
        }
    }
    
    /**
     * Health check endpoint for tenant service
     */
    @GetMapping("/health")
    public ResponseEntity<String> health() {
        return ResponseEntity.ok("Tenant service is healthy");
    }
}