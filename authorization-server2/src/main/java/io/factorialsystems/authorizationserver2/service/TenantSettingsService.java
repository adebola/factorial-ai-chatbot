package io.factorialsystems.authorizationserver2.service;

import io.factorialsystems.authorizationserver2.dto.TenantSettingsRequest;
import io.factorialsystems.authorizationserver2.dto.TenantSettingsResponse;
import io.factorialsystems.authorizationserver2.mapper.TenantMapper;
import io.factorialsystems.authorizationserver2.mapper.TenantSettingsMapper;
import io.factorialsystems.authorizationserver2.model.Tenant;
import io.factorialsystems.authorizationserver2.model.TenantSettings;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.stream.Collectors;

/**
 * Service for managing tenant settings
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class TenantSettingsService {
    
    private final TenantSettingsMapper tenantSettingsMapper;
    private final TenantMapper tenantMapper;
    private final RedisCacheService redisCacheService;
    
    private static final String CACHE_KEY_PREFIX = "tenant:settings:";
    
    /**
     * Get tenant settings by tenant ID, create with defaults if not exists
     */
    public TenantSettingsResponse getOrCreateSettings(String tenantId) {
        log.debug("Getting settings for tenant: {}", tenantId);
        
        // Check cache first
        TenantSettings cachedSettings = getCachedSettings(tenantId);
        if (cachedSettings != null) {
            log.debug("Settings found in cache for tenant: {}", tenantId);
            return toResponse(cachedSettings);
        }
        
        // Check database
        TenantSettings settings = tenantSettingsMapper.findByTenantId(tenantId);
        
        if (settings == null) {
            // Create default settings if they don't exist
            log.debug("Creating default settings for tenant: {}", tenantId);
            settings = createDefaultSettings(tenantId);
        }
        
        // Cache the result
        cacheSettings(settings);
        
        return toResponse(settings);
    }
    
    /**
     * Update tenant settings
     */
    @Transactional
    public TenantSettingsResponse updateSettings(String tenantId, TenantSettingsRequest request) {
        log.debug("Updating settings for tenant: {}", tenantId);
        
        // Verify tenant exists
        Tenant tenant = tenantMapper.findById(tenantId);
        if (tenant == null) {
            throw new IllegalArgumentException("Tenant not found: " + tenantId);
        }
        
        // Get existing settings or create defaults
        TenantSettings settings = tenantSettingsMapper.findByTenantId(tenantId);
        if (settings == null) {
            settings = createDefaultSettings(tenantId);
        }
        
        // Update only provided fields
        if (request.getPrimaryColor() != null) {
            validateHexColor(request.getPrimaryColor(), "Primary color");
            settings.setPrimaryColor(request.getPrimaryColor());
        }
        if (request.getSecondaryColor() != null) {
            validateHexColor(request.getSecondaryColor(), "Secondary color");
            settings.setSecondaryColor(request.getSecondaryColor());
        }
        if (request.getHoverText() != null) {
            settings.setHoverText(request.getHoverText());
        }
        if (request.getWelcomeMessage() != null) {
            settings.setWelcomeMessage(request.getWelcomeMessage());
        }
        if (request.getChatWindowTitle() != null) {
            settings.setChatWindowTitle(request.getChatWindowTitle());
        }
        if (request.getAdditionalSettings() != null) {
            settings.setAdditionalSettings(request.getAdditionalSettings());
        }
        
        // Update in database
        int updated = tenantSettingsMapper.updateByTenantId(settings);
        if (updated == 0) {
            throw new RuntimeException("Failed to update settings for tenant: " + tenantId);
        }
        
        // Refresh from database to get updated timestamp
        settings = tenantSettingsMapper.findByTenantId(tenantId);
        
        // Update cache
        evictSettingsCache(tenantId);
        cacheSettings(settings);
        
        log.debug("Successfully updated settings for tenant: {}", tenantId);
        return toResponse(settings);
    }
    
    /**
     * Delete tenant settings (soft delete)
     */
    @Transactional
    public boolean deleteSettings(String tenantId) {
        log.debug("Deleting settings for tenant: {}", tenantId);
        
        int deleted = tenantSettingsMapper.softDeleteByTenantId(tenantId);
        if (deleted > 0) {
            evictSettingsCache(tenantId);
            log.debug("Successfully deleted settings for tenant: {}", tenantId);
            return true;
        }
        
        return false;
    }
    
    /**
     * Get all tenant settings (admin only)
     */
    public List<TenantSettingsResponse> getAllSettings() {
        log.debug("Getting all tenant settings");
        
        List<TenantSettings> allSettings = tenantSettingsMapper.findAll();
        return allSettings.stream()
                .map(this::toResponse)
                .collect(Collectors.toList());
    }
    
    /**
     * Create default settings for a new tenant
     */
    @Transactional
    public TenantSettings createDefaultSettings(String tenantId) {
        log.debug("Creating default settings for tenant: {}", tenantId);
        
        // Verify tenant exists
        Tenant tenant = tenantMapper.findById(tenantId);
        if (tenant == null) {
            throw new IllegalArgumentException("Tenant not found: " + tenantId);
        }
        
        TenantSettings settings = new TenantSettings();
        settings.generateId();
        settings.setTenantId(tenantId);
        settings.setDefaults();
        
        tenantSettingsMapper.insert(settings);
        
        // Retrieve from database to get timestamps
        return tenantSettingsMapper.findByTenantId(tenantId);
    }
    
    /**
     * Get settings from cache
     */
    private TenantSettings getCachedSettings(String tenantId) {
        try {
            return redisCacheService.getCachedSettingsByTenantId(tenantId);
        } catch (Exception e) {
            log.warn("Failed to get settings from cache for tenant: {}", tenantId, e);
            return null;
        }
    }
    
    /**
     * Cache settings
     */
    private void cacheSettings(TenantSettings settings) {
        if (settings != null) {
            try {
                redisCacheService.cacheSettings(settings);
            } catch (Exception e) {
                log.warn("Failed to cache settings for tenant: {}", settings.getTenantId(), e);
            }
        }
    }
    
    /**
     * Evict settings from cache
     */
    private void evictSettingsCache(String tenantId) {
        try {
            redisCacheService.evictSettings(tenantId);
        } catch (Exception e) {
            log.warn("Failed to evict settings cache for tenant: {}", tenantId, e);
        }
    }
    
    /**
     * Validate hex color format
     */
    private void validateHexColor(String color, String fieldName) {
        if (!TenantSettings.isValidHexColor(color)) {
            throw new IllegalArgumentException(
                fieldName + " must be a valid hex color code (e.g., #FF5733), got: " + color
            );
        }
    }
    
    /**
     * Convert TenantSettings to response DTO
     */
    private TenantSettingsResponse toResponse(TenantSettings settings) {
        // Get tenant name for chat logo initials
        Tenant tenant = tenantMapper.findById(settings.getTenantId());
        String companyName = tenant != null ? tenant.getName() : null;
        
        return TenantSettingsResponse.builder()
                .id(settings.getId())
                .tenantId(settings.getTenantId())
                .primaryColor(settings.getPrimaryColor())
                .secondaryColor(settings.getSecondaryColor())
                .hoverText(settings.getHoverText())
                .welcomeMessage(settings.getWelcomeMessage())
                .chatWindowTitle(settings.getChatWindowTitle())
                .companyLogoUrl(settings.getCompanyLogoUrl())
                .chatLogo(settings.getChatLogoInfo(companyName))
                .additionalSettings(settings.getAdditionalSettings())
                .isActive(settings.getIsActive())
                .createdAt(settings.getCreatedAt())
                .updatedAt(settings.getUpdatedAt())
                .build();
    }
    
    /**
     * Update tenant logo settings
     */
    @Transactional
    public boolean updateTenantLogo(String tenantId, String logoUrl) {
        log.debug("Updating logo for tenant: {} with URL: {}", tenantId, logoUrl);
        
        try {
            // Check if tenant settings exist, create if they don't
            TenantSettings existingSettings = tenantSettingsMapper.findByTenantId(tenantId);
            if (existingSettings == null) {
                log.info("Creating default settings for tenant {} before updating logo", tenantId);
                createDefaultSettings(tenantId);
            }
            
            // Update logo in database
            int rowsUpdated = tenantSettingsMapper.updateTenantLogo(tenantId, logoUrl);
            
            if (rowsUpdated > 0) {
                // Clear cache to ensure fresh data on next access
                evictSettingsCache(tenantId);
                
                log.info("Successfully updated tenant {} logo to URL: {}", tenantId, logoUrl);
                return true;
            } else {
                log.warn("Failed to update tenant {} logo - no rows affected", tenantId);
                return false;
            }
            
        } catch (Exception e) {
            log.error("Error updating tenant {} logo to URL {}: {}", tenantId, logoUrl, e.getMessage(), e);
            return false;
        }
    }
    
    /**
     * Delete tenant logo
     */
    @Transactional
    public boolean deleteTenantLogo(String tenantId) {
        log.debug("Deleting logo for tenant: {}", tenantId);
        
        try {
            // Update logo URL to null in database
            int rowsUpdated = tenantSettingsMapper.updateTenantLogo(tenantId, null);
            
            if (rowsUpdated > 0) {
                // Clear cache to ensure fresh data on next access
                evictSettingsCache(tenantId);
                
                log.info("Successfully deleted tenant {} logo", tenantId);
                return true;
            } else {
                log.warn("Failed to delete tenant {} logo - no rows affected", tenantId);
                return false;
            }
            
        } catch (Exception e) {
            log.error("Error deleting tenant {} logo: {}", tenantId, e.getMessage(), e);
            return false;
        }
    }
}