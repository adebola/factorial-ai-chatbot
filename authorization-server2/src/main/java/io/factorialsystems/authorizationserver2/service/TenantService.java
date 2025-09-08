package io.factorialsystems.authorizationserver2.service;

import io.factorialsystems.authorizationserver2.mapper.TenantMapper;
import io.factorialsystems.authorizationserver2.model.Tenant;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.security.SecureRandom;
import java.time.OffsetDateTime;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class TenantService {
    
    private final TenantMapper tenantMapper;
    private final RedisCacheService cacheService;
    private static final SecureRandom secureRandom = new SecureRandom();
    private static final String ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
    
    public Tenant findById(String id) {
        // Check cache first
        Tenant cachedTenant = cacheService.getCachedTenant(id);
        if (cachedTenant != null) {
            return cachedTenant;
        }
        
        // Fetch from database and cache
        Tenant tenant = tenantMapper.findById(id);
        if (tenant != null) {
            cacheService.cacheTenant(tenant);
        }
        return tenant;
    }
    
    public Tenant findByDomain(String domain) {
        // Check cache first
        Tenant cachedTenant = cacheService.getCachedTenantByDomain(domain);
        if (cachedTenant != null) {
            return cachedTenant;
        }
        
        // Fetch from database and cache
        Tenant tenant = tenantMapper.findByDomain(domain);
        if (tenant != null) {
            cacheService.cacheTenant(tenant);
        }
        return tenant;
    }
    
    public Tenant findByName(String name) {
        return tenantMapper.findByName(name);
    }
    
    public Tenant findByApiKey(String apiKey) {
        // Check cache first
        Tenant cachedTenant = cacheService.getCachedTenantByApiKey(apiKey);
        if (cachedTenant != null) {
            return cachedTenant;
        }
        
        // Fetch from database and cache
        Tenant tenant = tenantMapper.findByApiKey(apiKey);
        if (tenant != null) {
            cacheService.cacheTenant(tenant);
        }
        return tenant;
    }
    
    /**
     * Generate a secure API key for the tenant using the same algorithm as the onboarding service
     * Generates a 64-character string using letters and digits
     */
    public String generateApiKey() {
        StringBuilder apiKey = new StringBuilder(64);
        for (int i = 0; i < 64; i++) {
            apiKey.append(ALPHABET.charAt(secureRandom.nextInt(ALPHABET.length())));
        }
        return apiKey.toString();
    }
              @Transactional
    public Tenant createTenant(String name, String domain, String description) {
        // Check if tenant already exists
        if (findByDomain(domain) != null) {
            throw new IllegalArgumentException("A tenant with this domain already exists");
        }
        
        if (findByName(name) != null) {
            throw new IllegalArgumentException("A tenant with this name already exists");
        }
        
        // Generate unique API key
        String apiKey = generateApiKey();
        while (tenantMapper.findByApiKey(apiKey) != null) {
            apiKey = generateApiKey();
        }
        
        // Create new tenant
        Tenant tenant = Tenant.builder()
                .id(UUID.randomUUID().toString())
                .name(name.trim())
                .domain(domain.toLowerCase().trim())
                .apiKey(apiKey)
                .isActive(true)
                .createdAt(OffsetDateTime.now())
                .updatedAt(OffsetDateTime.now())
                .build();
        
        int result = tenantMapper.insert(tenant);
        if (result <= 0) {
            throw new RuntimeException("Failed to create tenant");
        }
        
        log.info("Created new tenant: id={}, name={}, domain={}, apiKey={}", 
                tenant.getId(), tenant.getName(), tenant.getDomain(), 
                apiKey.substring(0, 8) + "..." // Log only first 8 characters for security
        );
        
        // Cache the newly created tenant
        cacheService.cacheTenant(tenant);
        
        return tenant;
    }
    
    @Transactional
    public Tenant updateTenant(Tenant tenant) {
        tenant.setUpdatedAt(OffsetDateTime.now());
        int result = tenantMapper.update(tenant);
        if (result <= 0) {
            throw new RuntimeException("Failed to update tenant");
        }
        
        log.info("Updated tenant: id={}, name={}, domain={}", tenant.getId(), tenant.getName(), tenant.getDomain());
        
        // Update cache with new tenant data
        cacheService.evictTenant(tenant.getId());
        cacheService.cacheTenant(tenant);
        
        return tenant;
    }
    
    public boolean isDomainAvailable(String domain) {
        return findByDomain(domain.toLowerCase().trim()) == null;
    }
    
    public boolean isNameAvailable(String name) {
        return findByName(name.trim()) == null;
    }
}