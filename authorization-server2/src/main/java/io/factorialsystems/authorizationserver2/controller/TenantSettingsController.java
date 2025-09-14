package io.factorialsystems.authorizationserver2.controller;

import io.factorialsystems.authorizationserver2.dto.TenantSettingsRequest;
import io.factorialsystems.authorizationserver2.dto.TenantSettingsResponse;
import io.factorialsystems.authorizationserver2.service.TenantSettingsService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * REST controller for tenant settings management
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/tenants")
@RequiredArgsConstructor
@Validated
public class TenantSettingsController {
    
    private final TenantSettingsService tenantSettingsService;
    
    /**
     * Get tenant settings by tenant ID
     */
    @GetMapping("/{tenantId}/settings")
//    @PreAuthorize("hasAuthority('SCOPE_tenant:read')")
    public ResponseEntity<TenantSettingsResponse> getTenantSettings(@PathVariable String tenantId) {
        log.info("Getting settings for tenant: {}", tenantId);
        
        try {
            TenantSettingsResponse settings = tenantSettingsService.getOrCreateSettings(tenantId);
            return ResponseEntity.ok(settings);
            
        } catch (IllegalArgumentException e) {
            log.warn("Tenant not found: {}", tenantId);
            return ResponseEntity.notFound().build();
            
        } catch (Exception e) {
            log.error("Failed to get settings for tenant: {}", tenantId, e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).build();
        }
    }
    
    /**
     * Update tenant settings
     */
    @PutMapping("/{tenantId}/settings")
//    @PreAuthorize("hasAuthority('SCOPE_tenant:write')")
    public ResponseEntity<TenantSettingsResponse> updateTenantSettings(
            @PathVariable String tenantId,
            @Valid @RequestBody TenantSettingsRequest request) {
        
        log.info("Updating settings for tenant: {}", tenantId);
        
        try {
            TenantSettingsResponse settings = tenantSettingsService.updateSettings(tenantId, request);
            return ResponseEntity.ok(settings);
            
        } catch (IllegalArgumentException e) {
            log.warn("Invalid request for tenant {}: {}", tenantId, e.getMessage());
            return ResponseEntity.badRequest().build();
            
        } catch (Exception e) {
            log.error("Failed to update settings for tenant: {}", tenantId, e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).build();
        }
    }
    
    /**
     * Delete tenant settings (soft delete)
     */
    @DeleteMapping("/{tenantId}/settings")
//    @PreAuthorize("hasAuthority('SCOPE_tenant:write')")
    public ResponseEntity<Map<String, Object>> deleteTenantSettings(@PathVariable String tenantId) {
        log.info("Deleting settings for tenant: {}", tenantId);
        
        try {
            boolean deleted = tenantSettingsService.deleteSettings(tenantId);
            
            if (deleted) {
                return ResponseEntity.ok(Map.of(
                    "message", "Tenant settings deleted successfully",
                    "tenant_id", tenantId
                ));
            } else {
                return ResponseEntity.notFound().build();
            }
            
        } catch (Exception e) {
            log.error("Failed to delete settings for tenant: {}", tenantId, e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(Map.of("error", "Failed to delete tenant settings"));
        }
    }
    
    /**
     * Get all tenant settings (admin only)
     */
    @GetMapping("/settings")
//    @PreAuthorize("hasAuthority('SCOPE_admin') or hasAuthority('ROLE_ADMIN')")
    public ResponseEntity<Map<String, Object>> getAllTenantSettings() {
        log.info("Getting all tenant settings (admin request)");
        
        try {
            List<TenantSettingsResponse> allSettings = tenantSettingsService.getAllSettings();
            
            return ResponseEntity.ok(Map.of(
                "settings", allSettings,
                "total", allSettings.size()
            ));
            
        } catch (Exception e) {
            log.error("Failed to get all tenant settings", e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(Map.of("error", "Failed to retrieve tenant settings"));
        }
    }
    
    /**
     * Create default settings for a tenant (admin only)
     */
    @PostMapping("/{tenantId}/settings")
//    @PreAuthorize("hasAuthority('SCOPE_admin') or hasAuthority('ROLE_ADMIN')")
    public ResponseEntity<TenantSettingsResponse> createDefaultSettings(@PathVariable String tenantId) {
        log.info("Creating default settings for tenant: {}", tenantId);
        
        try {
            // This will create default settings if they don't exist, or return existing ones
            TenantSettingsResponse settings = tenantSettingsService.getOrCreateSettings(tenantId);
            
            return ResponseEntity.status(HttpStatus.CREATED).body(settings);
            
        } catch (IllegalArgumentException e) {
            log.warn("Tenant not found: {}", tenantId);
            return ResponseEntity.notFound().build();
            
        } catch (Exception e) {
            log.error("Failed to create default settings for tenant: {}", tenantId, e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).build();
        }
    }
}